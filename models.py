from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String, nullable=False)
    name = Column(String)
    referral_code = Column(String, unique=True, index=True)
    referrer_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    has_access = Column(Boolean, default=False)  # New column to track access

    referrer = relationship('User', remote_side=[id], backref='referred_users')
    refresh_tokens = relationship("RefreshToken", back_populates="user")

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    token = Column(String, unique=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_revoked = Column(Boolean, default=False)

    user = relationship("User", back_populates="refresh_tokens", lazy='joined')