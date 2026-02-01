from sqlalchemy import create_engine, Column, String, Integer, DateTime, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

Base = declarative_base()
engine = create_engine(os.getenv('DATABASE_URL'))
Session = sessionmaker(bind=engine)

class User(Base):
    __tablename__ = 'users'
    
    telegram_id = Column(String, primary_key=True)
    outlook_email = Column(String)
    access_token = Column(Text)
    refresh_token = Column(Text)
    expires_at = Column(DateTime)
    
    # Auth state management
    auth_state = Column(Text, nullable=True)
    code_verifier = Column(Text, nullable=True)
    auth_requested_at = Column(DateTime, nullable=True)
    
    is_connected = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Email(Base):
    __tablename__ = 'emails'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(String)
    outlook_id = Column(String, unique=True)
    sender = Column(String)
    recipient = Column(String)
    subject = Column(Text)
    body = Column(Text)
    received_at = Column(DateTime)
    is_read = Column(Boolean, default=False)
    has_attachments = Column(Boolean, default=False)
    stored_at = Column(DateTime, default=datetime.utcnow)

# Create tables
Base.metadata.create_all(engine)
