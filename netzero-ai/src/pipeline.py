"""One-command local demo pipeline."""
import subprocess,sys,os
steps=[['src.data.generate_demo_data'],['src.forecasting.train_all']]
for mod in steps:
    print('RUN',mod[0]); subprocess.check_call([sys.executable,'-m',mod[0]])
print('\nPipeline complete. Start API with: uvicorn api.main:app --reload')
