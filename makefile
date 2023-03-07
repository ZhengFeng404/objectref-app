SHELL = /bin/bash

project_dependencies ?= $(addprefix $(project_root)/, \
		emissor \
		objectref \
		cltl-combot \
		cltl-requirements \
		cltl-backend \
		cltl-emissor-data \
		cltl-object-recognition \
		cltl-chat-ui)

git_remote ?= https://github.com/leolani

sources =

include util/make/makefile.base.mk
include util/make/makefile.py.base.mk
include util/make/makefile.git.mk
include makefile.helm.mk

.PHONY: build
build: venv

.PHONY: clean
clean: py-clean base-clean