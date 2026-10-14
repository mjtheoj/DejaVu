"""Compatibility facade for existing route handlers and helper imports.

New business logic belongs in app/core or app/services. This module re-exports
focused implementations while preserving imports used by existing routes/tests.
"""
from __future__ import annotations
import hashlib, json, math, os, secrets, sqlite3, uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Literal
from fastapi import Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError
from app.core.config import *
from app.core.database import *
from app.core.images import *
from app.core.security import *
from app.api.dependencies import *
from app.services.reports import *
from app.services.notifications import *
from app.services.rewards import *
