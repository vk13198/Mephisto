from models import db, Portfolio
from app import app


def init_db(seed_portfolio=True):
    """Create database tables and optionally seed a sample portfolio."""
    with app.app_context():
        db.create_all()
        if seed_portfolio:
            # Create a portfolio row if none exists
            if Portfolio.query.count() == 0:
                p = Portfolio(cash=100000.0, total_value=100000.0)
                db.session.add(p)
                db.session.commit()
                print('Seeded portfolio with 100000 cash')
        print('Database initialized')


if __name__ == '__main__':
    init_db()
