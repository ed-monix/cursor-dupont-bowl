# Definition of done (TASKS.md): `make check` green, `make dryrun` runs a full
# fake week from committed fixtures.
.PHONY: check dryrun

check:
	pytest -q

# Run the deterministic fake week against a THROWAWAY copy of the committed
# fixtures, so `make dryrun` is repeatable and never dirties tests/dryrun.
dryrun:
	@tmp=$$(mktemp -d); \
	cp -r tests/dryrun $$tmp/league; \
	python scripts/dryrun.py --root $$tmp/league; \
	status=$$?; \
	rm -rf $$tmp; \
	exit $$status
