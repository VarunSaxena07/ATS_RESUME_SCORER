import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import(
    ALLOWED_ORIGINS, 
    APP_DESCRIPTION, 
    APP_TITLE, 
    APP_VERSION, 
    SPACY_MODEL_PRIMARY, 
    SPACY_MODEL_SECONDARY, SENTENCE_TRANSFORMER_MODEL
)
from backend.api.routes import router

logger=logging.getLogger('ats_resume_scorer')

@asynccontextmanager
async def lifespan(app:FastAPI):
    logger.info('Starting ATS Resume Analyzer API...')

    import spacy
    app.state.nlp = _load_spacy_model(spacy)

    logger.info(f'Loading SentenceTransformer: {SENTENCE_TRANSFORMER_MODEL}')
    from sentence_transformers import SentenceTransformer
    app.state.embedder = SentenceTransformer(SENTENCE_TRANSFORMER_MODEL)
    logger.info(f'Loaded {SENTENCE_TRANSFORMER_MODEL}')

    logger.info('All models loaded. API is ready to serve requests.')

    yield

    logger.info('shutting down the api!!')


def _load_spacy_model(spacy):
    for model_name in (SPACY_MODEL_PRIMARY, SPACY_MODEL_SECONDARY):
        model_name = model_name.strip().strip('"').strip("'")
        if not model_name:
            continue
        logger.info(f'Loading spaCy NLP model: {model_name}')
        try:
            nlp = spacy.load(model_name)
            logger.info(f'Loaded {model_name}')
            return nlp
        except OSError as exc:
            logger.warning(f'{model_name} not found: {exc}')

    logger.warning(
        'No spaCy English model found; using blank English pipeline. '
        'NER-based checks will be limited until en_core_web_sm or en_core_web_md is installed.'
    )
    return spacy.blank('en')

app=FastAPI(
    title=APP_TITLE, 
    description=APP_DESCRIPTION, 
    version=APP_VERSION, 
    lifespan=lifespan,
    docs_url='/docs',
    redoc_url='/redoc'
)

app.add_middleware(
    CORSMiddleware, 
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True, 
    allow_methods     = ['*'],
    allow_headers     = ['*'],

)

app.include_router(router)

@app.get('/')
async def root():
    return {
        'name':      'ATS Resume Analyzer API',
        'version':   '2.0.0',
        'endpoints': {
            'POST   /api/v1/analyze-resume': 'Analyze a resume',
            'GET    /api/v1/history':        'Get user history',
            'DELETE /api/v1/history/:id':    'Delete a history entry',
            'GET    /api/v1/health':         'Health check',
            'POST   /api/v1/generate-pdf':   'Generate PDF report from data',
        },
    }


def _running_under_streamlit() -> bool:
    try:
        from streamlit.runtime.scriptrunner_utils.script_run_context import get_script_run_ctx
    except Exception:
        return False
    return get_script_run_ctx() is not None


if __name__ == '__main__' and not _running_under_streamlit():
    import uvicorn
    uvicorn.run(
        'backend.main:app',
        host    = '0.0.0.0',
        port    = 8000,
        reload  = True,    # Auto-restart on code changes (dev only)
    )
