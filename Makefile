.PHONY: dev test demo

dev:
	python run_demo.py --reload

test:
	python -m pytest -q

demo:
	python run_demo.py
