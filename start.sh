find /Users/aragossa/dzrprj/auroqa/auroqa -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; find /Users/aragossa/dzrprj/auroqa/auroqa -name "*.pyc" -delete 2>/dev/null; echo "✅ Cache cleared"
export KAFKA_HOST=localhost && export REDIS_HOST=localhost
export PYTHONPATH=/Users/aragossa/dzrprj/auroqa:$PYTHONPATH
cd /Users/aragossa/dzrprj/auroqa/auroqa
python3 main.py
