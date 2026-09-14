.PHONY: test check
test: check
	python3 -m unittest discover -s tests -v

check:
	python3 -m py_compile tools/*.py
	@set -e; for script in bin/* scripts/*.sh; do case $$script in *arch-container.sh) bash -n $$script ;; *) sh -n $$script ;; esac; done
	sh -n freebsd/ops/epithet-pkg-publish
	sh -n freebsd/ops/epithet-pkg-test
	bash -n tests/arch.sh
