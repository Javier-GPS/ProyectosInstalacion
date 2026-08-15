"""Run the local API with ``python -m luminaire_optimizer``."""

import uvicorn


if __name__ == "__main__":
    uvicorn.run("luminaire_optimizer.api:app", host="127.0.0.1", port=8760, reload=False)
