"""Menjalankan aplikasi UPA BK UTM.

Pemakaian:
    python run.py                  # server di http://0.0.0.0:8000
    PORT=9000 python run.py        # port lain
"""
import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=False,
    )
