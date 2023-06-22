import numpy as np
from cltl.backend.impl.cached_storage import CachedImageStorage
from emissor.persistence import ScenarioStorage
from emissor.representation.scenario import Modality, class_type

from cltl.object_recognition.api import Object


def load_img(scenario_id, storage_path, emissor_path):
    scenario = ScenarioStorage(emissor_path).load_scenario(scenario_id)
    for image_signal in scenario.get_signals(Modality.IMAGE):
        image = CachedImageStorage(storage_path).get(image_signal.id)

        # There should be only one bounding box in the segment
        object_annotations = [(mention.segment[0].bounds, annotation.value.label)
            for mention in image_signal.mentions
            for annotation in mention.annotations
            if annotation.type == class_type(Object)]

        print((min(image.depth[np.nonzero(image.depth)]), max(image.depth.flatten())), object_annotations)


# The label of the object should be the name of the object asked by the researcher "Where is Object X?"
# May need the api to where the info is stored and load it
def get_object_bounds(scenario_id, storage_path, emissor_path, object_label_asked):
    scenario = ScenarioStorage(emissor_path).load_scenario(scenario_id)
    for image_signal in scenario.get_signals(Modality.IMAGE):
        image = CachedImageStorage(storage_path).get(image_signal.id)
        # There should be only one bounding box in the segment
        object_bounds = [mention.segment[0].bounds
            for mention in image_signal.mentions
            for annotation in mention.annotations
            if annotation.type == class_type(Object) and annotation.value.label == object_label_asked]
        # y0 should be less than y1, so the default order of it may have some problem. and thus we place y1 in front of
        # No! The order is totally a mess.
        x0, y0, x1, y1 = object_bounds[0]
        object_bounds_class = Bounds(x0, x1, y0, y1)

        return object_bounds_class, image


def get_object_distance(scenario_id, storage_path, emissor_path, object_label_asked):
    object_bounds = get_object_bounds(scenario_id, storage_path, emissor_path, object_label_asked)[0]
    image = get_object_bounds(scenario_id, storage_path, emissor_path, object_label_asked)[1]

    # Is it the correct way to get depth?
    object_distance_array = image.depth[object_bounds.y0:object_bounds.y1, object_bounds.x0:object_bounds.x1]
    object_distance = np.min(object_distance_array[np.nonzero(object_distance_array)])

    return object_distance


def deictic_reference(scenario_id, storage_path, emissor_path, object_label_asked):
    object_distance = get_object_distance(scenario_id, storage_path, emissor_path, object_label_asked)
    # How can I send the result to the robot speech system?
    if object_distance <= 1:
        return "near"
    else:
        return "far"


def angle_rotated_to_object(scenario_id, storage_path, emissor_path, object_label_asked):
    object_bounds = get_object_bounds(scenario_id, storage_path, emissor_path, object_label_asked)[0]
    image = get_object_bounds(scenario_id, storage_path, emissor_path, object_label_asked)[1]

    object_pixels = [(object_bounds.y0+object_bounds.y1)/2, (object_bounds.x0+object_bounds.x1)/2]
    # if the robot wants to reset its fixation to the object, then it need to rotate horizontally and vertically
    # with the angle calculated below
    tan_horizontal_rotation_required = (object_pixels[1] - 320/2)/(320/2) * np.tan(image.view.width/2)
    horizontal_rotation_required = np.arctan(tan_horizontal_rotation_required)
    tan_vertical_rotation_required = (object_pixels[0] - 240/2)/(240/2) * np.tan(image.view.height/2)
    vertical_rotation_required = np.arctan(tan_vertical_rotation_required)
    angle_required = [vertical_rotation_required, horizontal_rotation_required]
    # What does the output mean?
    return angle_required


def relative_reference(scenario_id, storage_path, emissor_path, object_label_asked):
    angle_required = angle_rotated_to_object(scenario_id, storage_path, emissor_path, object_label_asked)
    h_angle = angle_required[1]
    # How can I send the result to the robot speech system?
    if h_angle < 0:
        return "on my left"
    elif h_angle == 0:
        return "in front of me"
    elif h_angle > 0:
        return "on my right"


if __name__ == '__main__':
    load_img("4a9f0633-2796-4230-94c3-1d4032aa0957", "storage/image", "storage/emissor")
    print(get_object_distance("4a9f0633-2796-4230-94c3-1d4032aa0957", "storage/image", "storage/emissor", "person"))
    print(angle_rotated_to_object("4a9f0633-2796-4230-94c3-1d4032aa0957", "storage/image", "storage/emissor", "person"))
    print(relative_reference("4a9f0633-2796-4230-94c3-1d4032aa0957", "storage/image", "storage/emissor", "person"))
