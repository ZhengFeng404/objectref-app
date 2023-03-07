import logging.config
import random
import time

import requests
from cltl.backend.api.backend import Backend
from cltl.backend.api.camera import CameraResolution, Camera
from cltl.backend.api.microphone import Microphone
from cltl.backend.api.storage import AudioStorage, ImageStorage
from cltl.backend.api.text_to_speech import TextToSpeech
from cltl.backend.impl.cached_storage import CachedAudioStorage, CachedImageStorage
from cltl.backend.impl.image_camera import ImageCamera
from cltl.backend.impl.sync_microphone import SynchronizedMicrophone
from cltl.backend.impl.sync_tts import SynchronizedTextToSpeech, TextOutputTTS
from cltl.backend.server import BackendServer
from cltl.backend.source.client_source import ClientAudioSource, ClientImageSource
from cltl.backend.source.console_source import ConsoleOutput
from cltl.backend.spi.audio import AudioSource
from cltl.backend.spi.image import ImageSource
from cltl.backend.spi.text import TextOutput
from cltl.chatui.api import Chats
from cltl.chatui.memory import MemoryChats
from cltl.combot.event.bdi import IntentionEvent
from cltl.combot.infra.config.k8config import K8LocalConfigurationContainer
from cltl.combot.infra.di_container import singleton
from cltl.combot.infra.event import Event
from cltl.combot.infra.event.memory import SynchronousEventBusContainer
from cltl.combot.infra.event_log import LogWriter
from cltl.combot.infra.resource.threaded import ThreadedResourceContainer
from cltl.eliza.api import Eliza
from cltl.eliza.eliza import ElizaImpl
from cltl.emissordata.api import EmissorDataStorage
from cltl.emissordata.file_storage import EmissorDataFileStorage
from cltl.gestures.gestures import GestureType
from cltl.object_recognition.api import ObjectDetector
from cltl.object_recognition.proxy import ObjectDetectorProxy
from cltl_service.backend.backend import BackendService
from cltl_service.backend.storage import StorageService
from cltl_service.bdi.service import BDIService
from cltl_service.chatui.service import ChatUiService
from cltl_service.combot.event_log.service import EventLogService
from cltl_service.context.service import ContextService
from cltl_service.eliza.service import ElizaService
from cltl_service.emissordata.client import EmissorDataClient
from cltl_service.emissordata.service import EmissorDataService
from cltl_service.intentions.init import InitService
from cltl_service.keyword.service import KeywordService
from cltl_service.object_recognition.service import ObjectRecognitionService
from emissor.representation.util import serializer as emissor_serializer
from flask import Flask
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.serving import run_simple

logging.config.fileConfig('config/logging.config', disable_existing_loggers=False)
logger = logging.getLogger(__name__)


class InfraContainer(SynchronousEventBusContainer, K8LocalConfigurationContainer, ThreadedResourceContainer):
    def start(self):
        pass

    def stop(self):
        pass


class RemoteTextOutput(TextOutput):
    def __init__(self, remote_url: str):
        self._remote_url = remote_url

    def consume(self, text: str, language=None):
        tts_headers = {'Content-type': 'text/plain'}

        # animation = gestures.BOW
        animation = f"{random.choice(list(GestureType))}"
        print("THIS IS WHAT YOU SHOULD VERBALIZE FOR US:", text, animation)

        response = f"\\^startTag({animation}){text}^stopTag({animation})"  #### cannot pass in strings with quotes!!

        requests.post(f"{self._remote_url}/text", data=response, headers=tts_headers)


class BackendContainer(InfraContainer):
    @property
    @singleton
    def audio_storage(self) -> AudioStorage:
        return CachedAudioStorage.from_config(self.config_manager)

    @property
    @singleton
    def image_storage(self) -> ImageStorage:
        return CachedImageStorage.from_config(self.config_manager)

    @property
    @singleton
    def audio_source(self) -> AudioSource:
        return ClientAudioSource.from_config(self.config_manager)

    @property
    @singleton
    def image_source(self) -> ImageSource:
        return ClientImageSource.from_config(self.config_manager)

    @property
    @singleton
    def text_output(self) -> TextOutput:
        config = self.config_manager.get_config("cltl.backend.text_output")
        remote_url = config.get("remote_url")
        if remote_url:
            return RemoteTextOutput(remote_url)
        else:
            return ConsoleOutput()

    @property
    @singleton
    def microphone(self) -> Microphone:
        return SynchronizedMicrophone(self.audio_source, self.resource_manager)

    @property
    @singleton
    def camera(self) -> Camera:
        config = self.config_manager.get_config("cltl.backend.image")

        return ImageCamera(self.image_source, config.get_float("rate"))

    @property
    @singleton
    def tts(self) -> TextToSpeech:
        return SynchronizedTextToSpeech(TextOutputTTS(self.text_output), self.resource_manager)

    @property
    @singleton
    def backend(self) -> Backend:
        return Backend(self.microphone, self.camera, self.tts)

    @property
    @singleton
    def backend_service(self) -> BackendService:
        return BackendService.from_config(self.backend, self.audio_storage, self.image_storage,
                                          self.event_bus, self.resource_manager, self.config_manager)

    @property
    @singleton
    def storage_service(self) -> StorageService:
        return StorageService(self.audio_storage, self.image_storage)

    @property
    @singleton
    def server(self) -> Flask:
        if not self.config_manager.get_config('cltl.backend').get_boolean("run_server"):
            # Return a placeholder
            return ""

        audio_config = self.config_manager.get_config('cltl.audio')
        video_config = self.config_manager.get_config('cltl.video')

        return BackendServer(audio_config.get_int('sampling_rate'), audio_config.get_int('channels'),
                             audio_config.get_int('frame_size'),
                             video_config.get_enum('resolution', CameraResolution),
                             video_config.get_int('camera_index'))

    def start(self):
        logger.info("Start Backend")
        super().start()
        if self.server:
            self.server.start()
        self.storage_service.start()
        self.backend_service.start()

    def stop(self):
        logger.info("Stop Backend")
        self.storage_service.stop()
        self.backend_service.stop()
        if self.server:
            self.server.stop()
        super().stop()


class EmissorStorageContainer(InfraContainer):
    @property
    @singleton
    def emissor_storage(self) -> EmissorDataStorage:
        return EmissorDataFileStorage.from_config(self.config_manager)

    @property
    @singleton
    def emissor_data_service(self) -> EmissorDataService:
        return EmissorDataService.from_config(self.emissor_storage,
                                              self.event_bus, self.resource_manager, self.config_manager)

    @property
    @singleton
    def emissor_data_client(self) -> EmissorDataClient:
        return EmissorDataClient("http://0.0.0.0:8000/emissor")

    def start(self):
        logger.info("Start Emissor Data Storage")
        super().start()
        self.emissor_data_service.start()

    def stop(self):
        logger.info("Stop Emissor Data Storage")
        self.emissor_data_service.stop()
        super().stop()


class ObjectRecognitionContainer(InfraContainer):
    @property
    @singleton
    def object_detector(self) -> ObjectDetector:
        config = self.config_manager.get_config("cltl.object_recognition")

        implementation = config.get("implementation")
        if not implementation:
            logger.warning("No ObjectDetector configured")
            return False
        if implementation != "proxy":
            raise ValueError("Unknown FaceEmotionExtractor implementation: " + implementation)

        config = self.config_manager.get_config("cltl.object_recognition.proxy")
        start_infra = config.get_boolean("start_infra")
        detector_url = config.get("detector_url") if "detector_url" in config else None

        return ObjectDetectorProxy(start_infra, detector_url)

    @property
    @singleton
    def object_recognition_service(self) -> ObjectRecognitionService:
        if self.object_detector:
            return ObjectRecognitionService.from_config(self.object_detector, self.event_bus,
                                                        self.resource_manager, self.config_manager)
        else:
            return False

    def start(self):
        super().start()
        if self.object_recognition_service:
            logger.info("Start Object Recognition")
            self.object_recognition_service.start()

    def stop(self):
        try:
            if self.object_recognition_service:
                logger.info("Stop Object Recognition")
                self.object_recognition_service.stop()
        finally:
            super().stop()


class ElizaComponentsContainer(EmissorStorageContainer, InfraContainer):
    @property
    @singleton
    def keyword_service(self) -> KeywordService:
        return KeywordService.from_config(self.emissor_data_client,
                                          self.event_bus, self.resource_manager, self.config_manager)

    @property
    @singleton
    def context_service(self) -> ContextService:
        return ContextService.from_config(self.event_bus, self.resource_manager, self.config_manager)

    @property
    @singleton
    def keyword_service(self) -> KeywordService:
        return KeywordService.from_config(self.emissor_data_client,
                                          self.event_bus, self.resource_manager, self.config_manager)

    @property
    @singleton
    def bdi_service(self) -> BDIService:
        # TODO make configurable
        bdi_model = {"init":
                         {"initialized": ["eliza"]},
                     "eliza":
                         {"quit": ["init"]}
                     }

        return BDIService.from_config(bdi_model, self.event_bus, self.resource_manager, self.config_manager)

    @property
    @singleton
    def init_intention(self) -> InitService:
        return InitService.from_config(self.emissor_data_client,
                                       self.event_bus, self.resource_manager, self.config_manager)

    def start(self):
        logger.info("Start Eliza services")
        super().start()
        self.bdi_service.start()
        self.keyword_service.start()
        self.context_service.start()
        self.init_intention.start()

    def stop(self):
        logger.info("Stop Eliza services")
        self.init_intention.stop()
        self.bdi_service.stop()
        self.keyword_service.stop()
        self.context_service.stop()
        super().stop()


class ChatUIContainer(InfraContainer):
    @property
    @singleton
    def chats(self) -> Chats:
        return MemoryChats()

    @property
    @singleton
    def chatui_service(self) -> ChatUiService:
        return ChatUiService.from_config(MemoryChats(), self.event_bus, self.resource_manager, self.config_manager)

    def start(self):
        logger.info("Start Chat UI")
        super().start()
        self.chatui_service.start()

    def stop(self):
        logger.info("Stop Chat UI")
        self.chatui_service.stop()
        super().stop()


class ElizaContainer(EmissorStorageContainer, InfraContainer):
    @property
    @singleton
    def eliza(self) -> Eliza:
        return ElizaImpl()

    @property
    @singleton
    def eliza_service(self) -> ElizaService:
        return ElizaService.from_config(self.eliza, self.emissor_data_client,
                                        self.event_bus, self.resource_manager, self.config_manager)

    def start(self):
        logger.info("Start Eliza")
        super().start()
        self.eliza_service.start()

    def stop(self):
        logger.info("Stop Eliza")
        self.eliza_service.stop()
        super().stop()


class ApplicationContainer(ElizaContainer, ElizaComponentsContainer,
                           ChatUIContainer,
                           EmissorStorageContainer, BackendContainer):
    @property
    @singleton
    def log_writer(self):
        config = self.config_manager.get_config("cltl.event_log")

        return LogWriter(config.get("log_dir"), serializer)

    @property
    @singleton
    def event_log_service(self):
        return EventLogService.from_config(self.log_writer, self.event_bus, self.config_manager)

    def start(self):
        logger.info("Start EventLog")
        super().start()
        self.event_log_service.start()

    def stop(self):
        try:
            logger.info("Stop EventLog")
            self.event_log_service.stop()
        finally:
            super().stop()


def serializer(obj):
    try:
        return emissor_serializer(obj)
    except Exception:
        try:
            return vars(obj)
        except Exception:
            return str(obj)


def main():
    ApplicationContainer.load_configuration()
    logger.info("Initialized Application")
    application = ApplicationContainer()

    with application as started_app:
        intention_topic = started_app.config_manager.get_config("cltl.bdi").get("topic_intention")
        started_app.event_bus.publish(intention_topic, Event.for_payload(IntentionEvent(["init"])))

        routes = {
            '/storage': started_app.storage_service.app,
            '/emissor': started_app.emissor_data_service.app,
            '/chatui': started_app.chatui_service.app,
            '/monitoring': started_app.monitoring_service.app,
        }

        if started_app.server:
            routes['/host'] = started_app.server.app

        web_app = DispatcherMiddleware(Flask("Objectref app"), routes)

        run_simple('0.0.0.0', 8000, web_app, threaded=True, use_reloader=False, use_debugger=False, use_evalex=True)

        intention_topic = started_app.config_manager.get_config("cltl.bdi").get("topic_intention")
        started_app.event_bus.publish(intention_topic, Event.for_payload(IntentionEvent(["terminate"])))
        time.sleep(1)


if __name__ == '__main__':
    main()
