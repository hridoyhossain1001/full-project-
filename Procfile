web: ENABLE_RETRY_IN_WEB=true uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 2
# worker: python -m app.services.retry_service  # আলাদা worker dyno থাকলে এটি আনকমেন্ট করুন ও ENABLE_RETRY_IN_WEB সরান
