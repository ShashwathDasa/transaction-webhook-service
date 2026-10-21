import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Transaction


@pytest.fixture
def test_db():
    engine = create_engine("postgresql+psycopg://postgres:postgres@127.0.0.1:5435/transactions_test",
                           pool_pre_ping=True, )

    Base.metadata.create_all(bind=engine)

    TestSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    try:
        with TestSessionLocal() as session:
            session.query(Transaction).delete()
            session.commit()

        yield TestSessionLocal

    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
