from __future__ import annotations

from datetime import date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Resident, ResidencePeriod, Room, User, utcnow
from app.services import today_local


def assert_room_available(
    db: Session,
    room_id: UUID,
    start_date: date,
    end_date: date | None,
    *,
    exclude_resident_id: UUID | None = None,
) -> Room:
    room = db.scalar(select(Room).where(Room.id == room_id).with_for_update())
    if not room or not room.is_active:
        raise HTTPException(status_code=422, detail="Tanlangan xona topilmadi yoki faol emas.")

    room_periods = db.scalars(
        select(ResidencePeriod).where(
            ResidencePeriod.room_id == room_id,
            ResidencePeriod.start_date < (end_date or date.max),
            or_(ResidencePeriod.end_date.is_(None), ResidencePeriod.end_date > start_date),
        )
    ).all()
    intervals: list[tuple[date, date | None]] = []
    for period in room_periods:
        if period.resident_id != exclude_resident_id:
            intervals.append((period.start_date, period.end_date))

    legacy_residents = db.scalars(
        select(Resident).where(
            Resident.room_id == room_id,
            Resident.is_archived.is_(False),
            Resident.id.not_in(select(ResidencePeriod.resident_id)),
        )
    ).all()
    for resident in legacy_residents:
        if resident.id != exclude_resident_id:
            intervals.append((resident.check_in_date or date.min, None))

    boundaries = {start_date}
    if end_date:
        boundaries.add(end_date)
    for interval_start, interval_end in intervals:
        if interval_start >= start_date and (end_date is None or interval_start < end_date):
            boundaries.add(interval_start)
        if interval_end and interval_end >= start_date and (end_date is None or interval_end < end_date):
            boundaries.add(interval_end)

    for day in boundaries:
        if end_date is not None and day >= end_date:
            continue
        concurrent = sum(1 for interval_start, interval_end in intervals if interval_start <= day and (interval_end is None or interval_end > day))
        if concurrent + 1 > room.capacity:
            raise HTTPException(status_code=409, detail="Tanlangan davrda xonada bo‘sh o‘rin qolmaydi.")
    return room


def record_room_assignment(
    db: Session,
    resident: Resident,
    room_id: UUID,
    start_date: date,
    end_date: date | None,
    actor: User | None,
) -> ResidencePeriod:
    existing_periods = db.scalars(
        select(ResidencePeriod)
        .where(ResidencePeriod.resident_id == resident.id)
        .order_by(ResidencePeriod.start_date.desc())
        .with_for_update()
    ).all()
    new_end = end_date or date.max
    overlapped: list[ResidencePeriod] = []
    for previous in existing_periods:
        previous_end = previous.end_date or date.max
        if previous.start_date < new_end and start_date < previous_end:
            if previous.room_id == room_id and previous.start_date == start_date and previous.end_date == end_date:
                return previous
            if previous.start_date >= start_date:
                raise HTTPException(status_code=409, detail="Yangi tayinlov avvalgi yashash davri bilan mos kelmaydi.")
            overlapped.append(previous)
    for previous in overlapped:
        if start_date <= previous.start_date:
            raise HTTPException(status_code=409, detail="Yangi tayinlov avvalgi yashash davri bilan mos kelmaydi.")
        previous.end_date = start_date
        previous.status = "ENDED"

    period = ResidencePeriod(
        resident_id=resident.id,
        room_id=room_id,
        start_date=start_date,
        end_date=end_date,
        status="PLANNED" if start_date > today_local() else "ENDED" if end_date is not None and end_date <= today_local() else "ACTIVE",
        created_by=actor.id if actor else None,
    )
    db.add(period)
    resident.room_id = room_id
    resident.check_in_date = start_date
    if end_date is not None:
        resident.is_archived = False
    return period


def close_open_period(db: Session, resident: Resident, ended_at: datetime | date | None = None) -> None:
    if isinstance(ended_at, date) and not isinstance(ended_at, datetime):
        end_date = ended_at
    else:
        end_date = ended_at.astimezone(ZoneInfo(settings.timezone)).date() if ended_at else today_local()
    periods = db.scalars(
        select(ResidencePeriod)
        .where(
            ResidencePeriod.resident_id == resident.id,
            or_(ResidencePeriod.end_date.is_(None), ResidencePeriod.end_date > end_date),
        )
        .order_by(ResidencePeriod.start_date.desc())
        .with_for_update()
    ).all()
    for period in periods:
        if end_date > period.start_date:
            period.end_date = end_date
            period.status = "ENDED"
        else:
            db.delete(period)
