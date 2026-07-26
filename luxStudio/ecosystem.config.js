module.exports = {
  apps: [{
    name: 'luxstudio-backend',
    cwd: './backend',
    script: './.venv/bin/python',
    args: '-m uvicorn app.main:app --host 0.0.0.0 --port 8750',
    env: { PYTHONPATH: '.' }
  }]
}
