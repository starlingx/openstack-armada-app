#
# Copyright 2017-2023 The Openstack-Helm Authors.
#
# Copyright (c) 2018-2023 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#

# It's necessary to set this because some environments don't link sh -> bash.
SHELL := /bin/bash
HELM  := helm
TASK  := build

EXCLUDES := helm-toolkit doc tests tools logs tmp zuul.d releasenotes
CHARTS := helm-toolkit $(filter-out $(EXCLUDES), $(patsubst %/.,%,$(wildcard */.)))

.PHONY: $(EXCLUDES) $(CHARTS)

all: $(CHARTS)

$(CHARTS):
	@if [ -d $@ ]; then \
		echo; \
		echo "===== Processing [$@] chart ====="; \
		make $(TASK)-$@; \
	fi

init-%:
	if [ -f $*/Makefile ]; then make -C $*; fi
	if [ -f $*/requirements.yaml ]; then $(HELM) dep up $*; fi

lint-%: init-%
	if [ -d $* ]; then $(HELM) lint $*; fi

build-%: lint-%
	if [ -d $* ]; then $(HELM) package $*; fi

# This is used exclusively with helm3 building in the gate to publish
package-%: init-%
	if [ -d $* ]; then helm package $*; fi

clean:
	@echo "Clean all build artifacts"
	rm -f */templates/_partials.tpl */templates/_globals.tpl
	rm -f *tgz */charts/*tgz */requirements.lock
	rm -rf */charts */tmpcharts

pull-all-images:
	@./tools/pull-images.sh

pull-images:
	@./tools/pull-images.sh $(filter-out $@,$(MAKECMDGOALS))

dev-deploy:
	@./tools/gate/devel/start.sh $(filter-out $@,$(MAKECMDGOALS))

%:
	@:
