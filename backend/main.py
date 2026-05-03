"""
CapEx Intelligence Platform - FastAPI Backend
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from backend.api.routes import companies, analysis
from backend.aichat.routes import router as aichat_router
from backend.api.routes import ingestion, sentiment, earnings, analytics, geographic, financials, alerts, company_detail, exports, supplemental_data
from backend.api.routes import reports as reports_router
from backend.api.routes import dashboard as dashboard_router
from backend.api.routes import intelligence as intelligence_router
from backend.hyperscaler.routes import router as hyperscaler_router
from backend.news.routes import router as news_router
from backend.analyst_view.routes import router as analyst_view_router
from backend.core.database import get_collection, get_collection_stats, get_embedding_model
from backend.ingestion.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        get_embedding_model()
        print("✓ Embedding model pre-loaded")
    except Exception as e:
        print(f"⚠ Embedding model failed to load: {e}")
    try:
        collection = get_collection()
        stats = get_collection_stats()
        print(f"✓ ChromaDB connected: {stats['total_documents']} documents")
    except Exception as e:
        print(f"⚠ ChromaDB connection failed: {e}")
    try:
        start_scheduler()
        print("✓ Scheduler started for automated SEC filing checks")
    except Exception as e:
        print(f"⚠ Scheduler failed to start: {e}")
    try:
        from backend.news.db import init_db
        init_db()
        print("✓ News config database ready")
    except Exception as e:
        print(f"⚠ News config database init failed: {e}")

    import asyncio
    async def warmup_cache_background():
        try:
            from backend.analytics.sentiment import analyze_company_sentiment
            from backend.analytics.classifier import classify_company_investments
            from backend.core.config import COMPANIES
            for ticker, config in list(COMPANIES.items())[:2]:
                company = config["name"].split()[0]
                try:
                    analyze_company_sentiment(company)
                    classify_company_investments(company)
                except:
                    pass
            print("✓ Cache warmed for initial companies")
        except Exception as e:
            print(f"⚠ Cache warmup failed: {e}")

        try:
            from backend.hyperscaler.financials import fetch_all_hyperscaler_financials
            from backend.hyperscaler.service import build_response_from_cache
            await asyncio.to_thread(fetch_all_hyperscaler_financials)
            build_response_from_cache()
            print("✓ Hyperscaler data pre-loaded")
        except Exception as e:
            print(f"⚠ Hyperscaler warmup failed: {e}")

        try:
            from backend.news.service import get_all_companies_news
            await get_all_companies_news()
            print("✓ News cache pre-loaded")
        except Exception as e:
            print(f"⚠ News warmup failed: {e}")

        for _fn_name, _fn_import in [
            ("sentiment",    lambda: __import__('backend.analytics.sentiment',    fromlist=['compare_company_sentiments']).compare_company_sentiments),
            ("classifier",   lambda: __import__('backend.analytics.classifier',   fromlist=['compare_investment_focus']).compare_investment_focus),
            ("trends",       lambda: __import__('backend.analytics.trends',       fromlist=['compare_company_trends']).compare_company_trends),
            ("anomaly",      lambda: __import__('backend.analytics.anomaly',      fromlist=['get_all_anomalies']).get_all_anomalies),
            ("geographic",   lambda: __import__('backend.analytics.geographic',   fromlist=['compare_geographic_footprints']).compare_geographic_footprints),
        ]:
            try:
                _fn = _fn_import()
                await asyncio.to_thread(_fn)
                print(f"  ✓ companies/{_fn_name} cached")
            except Exception as e:
                print(f"  ⚠ companies/{_fn_name} failed: {e}")
        print("✓ Companies analytics pre-loaded")

    asyncio.create_task(warmup_cache_background())
    yield
    print("Shutting down...")
    stop_scheduler()


app = FastAPI(
    title="Flex Competitive Intelligence Platform",
    description="AI-powered competitive intelligence analysis for EMS companies using RAG",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3000", "http://127.0.0.1:3001"],
    allow_origin_regex=r"https://.*\.trycloudflare\.com",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(aichat_router, prefix="/api", tags=["Chat"])
app.include_router(companies.router, prefix="/api", tags=["Companies"])
app.include_router(analysis.router, prefix="/api", tags=["Analysis"])
app.include_router(ingestion.router, prefix="/api", tags=["Ingestion"])
app.include_router(sentiment.router, prefix="/api", tags=["Sentiment"])
app.include_router(earnings.router, prefix="/api", tags=["Earnings"])
app.include_router(analytics.router, prefix="/api", tags=["Analytics"])
app.include_router(geographic.router, prefix="/api", tags=["Geographic"])
app.include_router(financials.router, prefix="/api", tags=["Financials"])
app.include_router(alerts.router, prefix="/api", tags=["Alerts"])
app.include_router(company_detail.router, prefix="/api", tags=["Company Detail"])
app.include_router(news_router, prefix="/api", tags=["News"])
app.include_router(analyst_view_router, prefix="/api", tags=["Analyst View"])
app.include_router(exports.router, prefix="/api", tags=["Exports"])
app.include_router(intelligence_router.router, prefix="/api/intelligence", tags=["Competitive Intelligence"])
app.include_router(hyperscaler_router, prefix="/api/intelligence", tags=["Hyperscaler"])
app.include_router(supplemental_data.router, prefix="/api", tags=["Supplemental Data"])
app.include_router(reports_router.router, prefix="/api", tags=["Reports & Calendar"])
app.include_router(dashboard_router.router, prefix="/api", tags=["Dashboard"])


@app.get("/")
async def root():
    return {"status": "healthy", "service": "Flex Competitive Intelligence Platform", "version": "1.0.0"}


@app.get("/api/health")
async def health_check():
    try:
        stats = get_collection_stats()
        return {"status": "healthy", "chromadb": {"connected": True, "documents": stats["total_documents"], "companies": stats["companies"]}}
    except Exception as e:
        return {"status": "degraded", "chromadb": {"connected": False, "error": str(e)}}


@app.get("/api/stats")
async def get_stats():
    return get_collection_stats()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001, reload=True)
