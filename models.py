from sqlalchemy import Column, String, Boolean, DateTime, Date
from sqlalchemy.sql import func
from database import Base


class Attendee(Base):
    __tablename__ = "attendees"

    id            = Column(String, primary_key=True, index=True)
    name          = Column(String, nullable=False)
    email         = Column(String, unique=True, nullable=False, index=True)
    phone         = Column(String, nullable=True)
    ticket_sent   = Column(Boolean, default=False)
    checked_in_day1 = Column(Boolean, default=False)
    checked_in_day2 = Column(Boolean, default=False)
    checkin_day1_at = Column(DateTime(timezone=True), nullable=True)
    checkin_day2_at = Column(DateTime(timezone=True), nullable=True)
    registered_at = Column(DateTime(timezone=True), server_default=func.now())
