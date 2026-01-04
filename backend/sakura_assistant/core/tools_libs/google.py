import os
from datetime import datetime
import pytz
from typing import Optional
from langchain_core.tools import tool
from .common import get_google_creds, retry_with_auth, USER_TIMEZONE
from googleapiclient.discovery import build
import base64
from email.mime.text import MIMEText

# --- Gmail Tools ---

@tool
@retry_with_auth
def gmail_read_email(
    query: Optional[str] = None,
    max_results: int = 5,
    unread_only: bool = False
) -> str:
    """
    Read emails with flexible filtering.
    Args:
        query: Gmail search query. Examples:
               - "from:user@example.com"
               - "subject:invoice"
               - "after:2024/01/01"
               - "is:unread"
               - "has:attachment"
        max_results: Max emails to return (default 5, max 20)
        unread_only: Only show unread emails (default False)
    """
    print("Called Gmail Read")
    creds = get_google_creds()
    if not creds: return "❌ Google Auth failed. Check token.json."
    
    try:
        service = build('gmail', 'v1', credentials=creds)
        
        # Build query
        q_parts = []
        if query:
            q_parts.append(query)
        if unread_only:
            q_parts.append("is:unread")
        q = " ".join(q_parts) if q_parts else "label:INBOX"
        
        # Cap max_results
        max_results = min(max_results, 20)
        
        results = service.users().messages().list(userId='me', q=q, maxResults=max_results).execute()
        messages = results.get('messages', [])
        
        if not messages: return "📭 No emails found matching your criteria."
        
        out = []
        for msg in messages:
            m = service.users().messages().get(userId='me', id=msg['id']).execute()
            snippet = m.get('snippet', '')
            headers = m['payload']['headers']
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '(No Subject)')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), '(Unknown)')
            date = next((h['value'] for h in headers if h['name'] == 'Date'), '')
            
            # Clean up sender
            if '<' in sender:
                sender = sender.split('<')[0].strip().strip('"')
            
            out.append(f"📧 FROM: {sender}\n   DATE: {date[:16] if date else 'N/A'}\n   SUBJ: {subject}\n   BODY: {snippet[:100]}...")
            
        return "\n\n".join(out)
    except Exception as e:
        return f"❌ Gmail error: {e}"

@tool
@retry_with_auth
def gmail_send_email(to: str, subject: str, body: str) -> str:
    """Send an email."""
    print("Called Gmail send")
    creds = get_google_creds()
    if not creds: return "❌ Google Auth failed."
    
    try:
        service = build('gmail', 'v1', credentials=creds)
        message = MIMEText(body)
        message['to'] = to
        message['subject'] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        
        service.users().messages().send(userId='me', body={'raw': raw}).execute()
        return f"📨 Email sent to {to}."
    except Exception as e:
        return f"❌ Send failed: {e}"

# --- Calendar Tools ---

@tool
@retry_with_auth
def calendar_get_events(
    date: Optional[str] = None,
    exclude_keywords: Optional[str] = None,
    include_birthdays: bool = True,
    max_results: int = 10
) -> str:
    """
    Get calendar events with flexible filtering.
    Args:
        date: Date format YYYY-MM-DD (defaults to today)
        exclude_keywords: Comma-separated keywords to exclude (e.g. "birthday,bday")
        include_birthdays: Whether to include birthday events (default True)
        max_results: Max events to return (default 10)
    """
    creds = get_google_creds()
    if not creds: return "❌ Google Auth failed."
    
    try:
        print("Called Calendar get")
        service = build('calendar', 'v3', credentials=creds)
        
        # Parse exclude keywords
        exclude_set = set()
        if exclude_keywords:
            exclude_set = {kw.strip().lower() for kw in exclude_keywords.split(",")}
        
        # Calculate timeMin
        tz = pytz.timezone(USER_TIMEZONE)
        if date:
            try:
                dt = datetime.strptime(date, "%Y-%m-%d")
                dt = tz.localize(dt)
            except:
                dt = datetime.now(tz)
        else:
            dt = datetime.now(tz)
            
        time_min = dt.isoformat()
        
        # 1. Primary Calendar
        events_result = service.events().list(
            calendarId='primary', 
            timeMin=time_min,
            maxResults=max_results, 
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])
        
        out = []
        for event in events:
            summary = event.get('summary', '(No Title)')
            # Apply keyword filter
            summary_lower = summary.lower()
            if any(kw in summary_lower for kw in exclude_set):
                continue
                
            start = event['start'].get('dateTime', event['start'].get('date'))
            try:
                start_dt = datetime.fromisoformat(start)
                start_str = start_dt.strftime("%I:%M %p, %b %d")
            except:
                start_str = start
            out.append(f"🗓️ {start_str} - {summary}")
        
        # 2. Birthdays Calendar
        if include_birthdays:
            try:
                birthday_id = 'addressbook#contacts@group.v.calendar.google.com'
                b_results = service.events().list(
                    calendarId=birthday_id, 
                    timeMin=time_min,
                    maxResults=5, 
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
                b_events = b_results.get('items', [])
                for b in b_events:
                    summary = b.get('summary', 'Birthday')
                    if any(kw in summary.lower() for kw in exclude_set):
                        continue
                    start = b['start'].get('date')
                    out.append(f"🎂 {start} - {summary}")
            except Exception:
                pass
            
        if not out: return "📅 No upcoming events matching filters."
        
        return "\n".join(out)
    except Exception as e:
        return f"❌ Calendar error: {e}"

@tool
@retry_with_auth
def calendar_create_event(title: str, start_time: str, end_time: str) -> str:
    """Create a calendar event. Times must be ISO format (YYYY-MM-DDTHH:MM:SS)."""
    creds = get_google_creds()
    if not creds: return "❌ Google Auth failed."
    
    try:
        print("Called Calendar create")
        service = build('calendar', 'v3', credentials=creds)
        event = {
            'summary': title,
            'start': {'dateTime': start_time, 'timeZone': USER_TIMEZONE},
            'end': {'dateTime': end_time, 'timeZone': USER_TIMEZONE},
        }
        event = service.events().insert(calendarId='primary', body=event).execute()
        return f"✅ Event created: {event.get('htmlLink')}"
    except Exception as e:
        return f"❌ Create event failed: {e}"

# --- Tasks Tools ---

@tool
@retry_with_auth
def tasks_list(show_completed: bool = False, max_results: int = 20) -> str:
    """List Google Tasks with filtering."""
    creds = get_google_creds()
    if not creds: return "❌ Google Auth failed."
    print("Called Tasks list")
    try:
        service = build('tasks', 'v1', credentials=creds)
        tasklists = service.tasklists().list().execute()
        if not tasklists.get('items'): return "❌ No task lists found."
        
        list_id = tasklists['items'][0]['id']
        params = {
            'tasklist': list_id,
            'maxResults': max_results,
            'showCompleted': show_completed,
            'showHidden': show_completed
        }
        tasks = service.tasks().list(**params).execute()
        items = tasks.get('items', [])
        if not items: return "✅ No tasks found."
        
        out = []
        for t in items:
            status = "☑️" if t.get('status') == 'completed' else "☐"
            title = t.get('title', '(No Title)')
            due = t.get('due', '')
            if due:
                try:
                    due_dt = datetime.fromisoformat(due.replace('Z', '+00:00'))
                    due_str = f" (Due: {due_dt.strftime('%b %d')})"
                except:
                    due_str = f" (Due: {due[:10]})"
            else:
                due_str = ""
            out.append(f"{status} {title}{due_str}")
        return "\n".join(out)
    except Exception as e:
        return f"❌ Tasks error: {e}"

@tool
@retry_with_auth
def tasks_create(title: str, notes: Optional[str] = None) -> str:
    """Create a Google Task."""
    print("Called Tasks create")
    creds = get_google_creds()
    if not creds: return "❌ Google Auth failed."
    try:
        service = build('tasks', 'v1', credentials=creds)
        tasklists = service.tasklists().list().execute()
        list_id = tasklists['items'][0]['id']
        task = {'title': title, 'notes': notes}
        service.tasks().insert(tasklist=list_id, body=task).execute()
        return f"✅ Task added: {title}"
    except Exception as e:
        return f"❌ Create task failed: {e}"
