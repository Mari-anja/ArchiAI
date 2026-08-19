import os
import uvicorn

if __name__ == "__main__":
    uvicorn.run("archiai.service.app:app",
                host=os.environ.get("HOST", "0.0.0.0"),
                port=int(os.environ.get("PORT", "8080")),
                workers=int(os.environ.get("WEB_CONCURRENCY", "1")))
