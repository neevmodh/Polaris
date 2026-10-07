@echo off
python -m src.data.generate_demo_data
python -m src.forecasting.train_all
uvicorn api.main:app --reload
