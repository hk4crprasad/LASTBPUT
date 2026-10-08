from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from app.core.db import engine
from app.core.settings import settings
app = FastAPI(title='Hospital GreenOps AI',version='1.0.0',openapi_url='/api/v1/openapi.json')
@app.get('/api/v1/health/live')
def live():
    return {'status':'live'}
@app.get('/api/v1/health/ready')
def ready():
    try:
        with engine.connect() as db:
            role=db.execute(text('SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user')).one()
            if any(role):raise RuntimeError('Unsafe runtime database role')
            revision=db.execute(text('SELECT version_num FROM alembic_version')).scalar()
            if revision!='0006':raise RuntimeError('Database schema revision unavailable or outdated')
        import redis
        from app.core.object_store import object_store
        redis.Redis.from_url(settings().redis_url).ping()
        object_store().probe()
        return {'status':'ready','database':'ok','redis':'ok','object_storage':'ok'}
    except Exception as e:
        return JSONResponse(status_code=503,content={'status':'unready','dependency_error':type(e).__name__})
import logging
import time
from uuid import uuid4
from fastapi import Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from app.routes import router
app.include_router(router)
app.add_middleware(CORSMiddleware,allow_origins=settings().cors_origins.split(','),allow_credentials=True,
                   allow_methods=['GET','POST','PATCH','DELETE'],allow_headers=['Content-Type','X-CSRF-Token','Idempotency-Key','Last-Event-ID'])
@app.middleware('http')
async def request_tracking(request:Request,call_next):
    request.state.request_id=str(uuid4());start=time.monotonic()
    response=await call_next(request)
    response.headers['X-Request-ID']=request.state.request_id
    logging.getLogger('greenops').info('%s %s %s %.3fs request=%s',request.method,request.url.path,response.status_code,time.monotonic()-start,request.state.request_id)
    return response
@app.exception_handler(HTTPException)
async def http_error(request,exc):
    return JSONResponse(status_code=exc.status_code,content={'error':{'code':str(exc.status_code),'message':exc.detail,'request_id':getattr(request.state,'request_id',None)}})
@app.exception_handler(RequestValidationError)
async def validation_error(request,exc):
    return JSONResponse(status_code=422,content={'error':{'code':'validation','message':'Request validation failed','details':[{'loc':list(e['loc']),'message':e['msg']} for e in exc.errors()]}})

from sqlalchemy.exc import SQLAlchemyError
@app.exception_handler(SQLAlchemyError)
async def database_error(request,exc):
    logging.getLogger('greenops').error('database_error type=%s request=%s',type(exc).__name__,getattr(request.state,'request_id',None))
    return JSONResponse(status_code=503,content={'error':{'code':'database_unavailable','message':'Database operation unavailable; retry or inspect the request ID','request_id':getattr(request.state,'request_id',None)}})

@app.exception_handler(Exception)
async def unexpected_error(request,exc):
    logging.getLogger('greenops').error('operation_error type=%s request=%s',type(exc).__name__,getattr(request.state,'request_id',None))
    return JSONResponse(status_code=500,content={'error':{'code':'operation_failed','message':'Operation failed; inspect the request ID and dependency status','request_id':getattr(request.state,'request_id',None)}})
