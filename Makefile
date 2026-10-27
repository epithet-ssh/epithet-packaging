.PHONY: test check
test: check
	python3 -m unittest discover -s tests -v

check:
	python3 -m py_compile tools/*.py
	@set -e; for script in bin/* scripts/*.sh freebsd/port/files/*.sh freebsd/port/files/*.in; do case $$script in *arch-container.sh|*debian-container.sh) bash -n $$script ;; *) sh -n $$script ;; esac; done
	sh -n freebsd/ops/epithet-pkg-publish
	sh -n freebsd/ops/epithet-pkg-test
	bash -n tests/arch.sh
	bash -n tests/debian.sh
