.PHONY: help demo test api ui docker clean

help:
	@echo "PipeCore — make targets"
	@echo "  make demo     run the zero-dependency data-plane compile demo"
	@echo "  make test     run all unit tests (data-plane + control-plane)"
	@echo "  make api      run the control-plane API + dashboard (uvicorn)"
	@echo "  make netns    live shaping proof in a network namespace (needs sudo)"
	@echo "  make docker   bring up the full stack with docker compose"
	@echo "  make clean    remove local db / caches"

demo:
	python3 data-plane/demo/compile_demo.py

test:
	pytest data-plane/tests control-plane/tests -q

api:
	cd control-plane && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

netns:
	sudo data-plane/demo/netns_demo.sh 30

docker:
	docker compose up --build

clean:
	rm -f control-plane/pipecore.db
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +
