#!/usr/bin/env python3
"""
Life Progress API
Calculates year, month, day, and life progress percentages.
Displays daily motivational quotes about time.

Configuration:
  - BIRTH_DATE: Your birth date
  - TARGET_AGE: Target lifespan for life progress calculation
"""

from flask import Flask, jsonify
from datetime import datetime, date
import calendar
import os

app = Flask(__name__)

# Configuration (can be overridden via environment variables)
BIRTH_YEAR = int(os.getenv('BIRTH_YEAR', 1996))
BIRTH_MONTH = int(os.getenv('BIRTH_MONTH', 10))
BIRTH_DAY = int(os.getenv('BIRTH_DAY', 14))
TARGET_AGE = int(os.getenv('TARGET_AGE', 80))

BIRTH_DATE = date(BIRTH_YEAR, BIRTH_MONTH, BIRTH_DAY)

# 30 motivational quotes about time and mortality
QUOTES = [
    "Time is the most valuable thing a man can spend. - Theophrastus",
    "Lost time is never found again. - Benjamin Franklin",
    "The trouble is, you think you have time. - Buddha",
    "The way we spend our days is the way we spend our lives. - Annie Dillard",
    "You may delay, but time will not. - Benjamin Franklin",
    "Time flies over us, but leaves its shadow behind. - Nathaniel Hawthorne",
    "The cost of a thing is the amount of life required to be exchanged for it. - Henry David Thoreau",
    "It is not that we have a short time to live, but that we waste a lot of it. - Seneca",
    "Life is short, and it is up to you to make it sweet. - Sarah Louise Delany",
    "Do not dwell in the past, do not dream of the future, concentrate the mind on the present moment. - Buddha",
    "In the end, it is not the years in your life that count. It is the life in your years. - Abraham Lincoln",
    "Time is what we want most, but what we use worst. - William Penn",
    "Yesterday is gone. Tomorrow has not yet come. We have only today. Let us begin. - Mother Teresa",
    "The only way to do great work is to love what you do. - Steve Jobs",
    "Memento mori - Remember that you will die. - Ancient Stoic Wisdom",
    "Every moment is a fresh beginning. - T.S. Eliot",
    "Time is a created thing. To say 'I don't have time' is to say 'I don't want to'. - Lao Tzu",
    "The two most powerful warriors are patience and time. - Leo Tolstoy",
    "Time takes it all, whether you want it to or not. - Stephen King",
    "Your time is limited, don't waste it living someone else's life. - Steve Jobs",
    "The bad news is time flies. The good news is you're the pilot. - Michael Altshuler",
    "Time is more valuable than money. You can get more money, but you cannot get more time. - Jim Rohn",
    "Don't count the days, make the days count. - Muhammad Ali",
    "Time is the coin of your life. Only you can determine how it will be spent. - Carl Sandburg",
    "The present time has one advantage over every other: it is our own. - Charles Caleb Colton",
    "How we spend our days is how we spend our lives. - Annie Dillard",
    "Time is the wisest counselor of all. - Pericles",
    "Better three hours too soon than a minute too late. - William Shakespeare",
    "Time flies like an arrow; fruit flies like a banana. - Groucho Marx",
    "The future is something which everyone reaches at the rate of 60 minutes an hour. - C.S. Lewis"
]


def get_daily_quote():
    today = date.today()
    day_of_year = today.timetuple().tm_yday
    return QUOTES[day_of_year % len(QUOTES)]


def calculate_progress():
    now = datetime.now()
    today = date.today()

    # Year progress
    year_start = datetime(now.year, 1, 1)
    year_end = datetime(now.year + 1, 1, 1)
    year_progress = ((now - year_start).total_seconds() / (year_end - year_start).total_seconds()) * 100

    # Month progress
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    month_progress = ((now.day - 1 + now.hour/24 + now.minute/1440) / days_in_month) * 100

    # Day progress
    day_progress = ((now.hour * 3600 + now.minute * 60 + now.second) / 86400) * 100

    # Life progress
    target_date = date(BIRTH_DATE.year + TARGET_AGE, BIRTH_DATE.month, BIRTH_DATE.day)
    total_life_days = (target_date - BIRTH_DATE).days
    days_lived = (today - BIRTH_DATE).days
    life_progress = (days_lived / total_life_days) * 100

    return {
        "year": round(year_progress, 1),
        "month": round(month_progress, 1),
        "day": round(day_progress, 1),
        "life": round(life_progress, 1),
        "age": round(days_lived / 365.25, 1),
        "remaining_years": round((total_life_days - days_lived) / 365.25, 1),
        "remaining_days": total_life_days - days_lived,
        "quote": get_daily_quote(),
        "target_age": TARGET_AGE
    }


@app.route('/progress')
def progress():
    return jsonify(calculate_progress())


@app.route('/health')
def health():
    return jsonify({"status": "healthy"})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5051)
