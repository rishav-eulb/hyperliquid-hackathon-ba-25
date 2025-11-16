"""
Database models for vault data storage
"""

from sqlalchemy import Column, String, Float, DateTime, Integer
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class VaultData(Base):
    """Model for storing vault yield data"""
    __tablename__ = 'vault_data'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    vault_address = Column(String(42), nullable=False, index=True)
    historical_apy = Column(Float, nullable=True)
    diluted_apy = Column(Float, nullable=True)
    tvl = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f"<VaultData(vault={self.vault_address}, apy={self.diluted_apy}, tvl={self.tvl})>"
    
    def to_dict(self):
        """Convert model to dictionary"""
        return {
            'id': self.id,
            'vault_address': self.vault_address,
            'historical_apy': self.historical_apy,
            'diluted_apy': self.diluted_apy,
            'tvl': self.tvl,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

