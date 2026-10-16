import argparse

from sqlalchemy import select

from app.bootstrap import bootstrap
from app.db import SessionLocal
from app.models import Room, SystemSetting


def main() -> None:
    parser = argparse.ArgumentParser(description="DormFlow initial operator bootstrap")
    parser.add_argument("--demo", action="store_true", help="Create optional demonstration rooms only")
    args = parser.parse_args()
    with SessionLocal() as db:
        bootstrap(db)
        if args.demo and not db.scalar(select(Room.id).limit(1)):
            db.add_all([
                Room(number="101", floor=1, capacity=4, notes="Namuna xona"),
                Room(number="102", floor=1, capacity=4, notes="Namuna xona"),
                Room(number="201", floor=2, capacity=3, notes="Namuna xona"),
            ])
            db.commit()
    print("DormFlow operator hisobi tayyor.")


if __name__ == "__main__":
    main()
