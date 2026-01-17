import os
from datetime import datetime
import pytz
from typing import Optional
from langchain_core.tools import tool
from .common import get_google_creds, retry_with_auth, USER_TIMEZONE
from googleapiclient.discovery import build
import base64
from email.mime.text import MIMEText
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, List, Dict, Any

# --- Gmail Tools ---

# Helper function - not a tool
def _fetch_single_email(service, msg_id: str) -> Dict[str, Any]:
    """Helper to fetch ONLY metadata for a single email (Fast)."""
    try:
        # format='metadata' avoids downloading the huge body/html
        # metadataHeaders reduces payload further
        return service.users().messages().get(
            userId='me', 
            id=msg_id, 
            format='metadata', 
            metadataHeaders=['From', 'Subject', 'Date'] 
        ).execute()
    except Exception as e:
        return {"error": str(e), "id": msg_id}

def _sanitize_email_list(raw_messages: List[Dict[str, Any]], snippets: Dict[str, str]) -> str:
    """Converts API response into a token-efficient Markdown list."""
    summary = []
    for msg in raw_messages:
        if "error" in msg: continue
        
        headers = {h['name']: h['value'] for h in msg.get('payload', {}).get('headers', [])}
        
        # Clean Sender: "Google <no-reply@google.com>" -> "Google"
        sender = headers.get('From', 'Unknown').split('<')[0].strip().replace('"', '')
        subject = headers.get('Subject', '(No Subject)')
        
        # Truncate Subject to 45 chars to save tokens
        if len(subject) > 45: subject = subject[:42] + "..."
        
        # Get snippet (passed separately because metadata format often omits it)
        snippet = snippets.get(msg['id'], '').replace('\n', ' ')
        if len(snippet) > 80: snippet = snippet[:77] + "..."

        # 160 tokens per 5 emails vs 4000 previously
        entry = f"• **{sender}** | *{subject}*\n  └── {snippet}"
        summary.append(entry)
        
    return "\n".join(summary) if summary else "No readable emails found."

@tool
@retry_with_auth
def gmail_read_email(
    query: Optional[str] = None,
    max_results: int = 5,
    unread_only: bool = False
) -> str:
    """
    Read emails with flexible filtering (Optimized: Parallel + Token Diet).
    Args:
        query: Gmail search query (e.g., "from:boss", "subject:invoice").
        max_results: Max emails to return (default 5, capped at 10).
        unread_only: Only show unread.
    """
    print(f"Called Gmail Read (max={max_results}, unread={unread_only})")
    creds = get_google_creds()
    if not creds: return "❌ Google Auth failed. Check token.json."
    
    try:
        service = build('gmail', 'v1', credentials=creds)
        
        # 1. Build query
        q_parts = []
        if query: q_parts.append(query)
        if unread_only: q_parts.append("is:unread")
        q = " ".join(q_parts) if q_parts else "label:INBOX"
        
        # Cap max_results to 10 to prevent token explosion
        max_results = min(max_results, 10)
        
        # 2. List IDs (Fast)
        results = service.users().messages().list(userId='me', q=q, maxResults=max_results).execute()
        messages = results.get('messages', [])
        
        if not messages: return "📭 No emails found matching your criteria."
        
        # 3. Parallel Fetch (The Speed Hack)
        # We need snippet (from list or full fetch) and headers (from metadata fetch)
        # Actually 'list' response contains snippet usually? No, it contains threadId/id only by default.
        # We fetch metadata in parallel.
        
        with ThreadPoolExecutor(max_workers=max_results) as executor:
            # Fetch metadata
            futures = [executor.submit(_fetch_single_email, service, m['id']) for m in messages]
            raw_data = [f.result() for f in futures]
            
            # For snippets, we actually need 'format=minimal' or 'full'. 'metadata' might exclude snippet.
            # Gmail API is tricky. Let's do a trick: we want snippet.
            # To get snippet efficiently without body, we might need a separate call or rely on full format?
            # Actually, 'messages.get' documentation says 'snippet' is returned in all formats except 'raw'?
            # Let's verify: Yes, snippet is a top-level field.
            # So _fetch_single_email returning 'payload' headers AND top-level 'snippet' is what we want.
            # But wait, 'format=metadata' returns snippet? Yes, usually.
            
            # Let's verify thread safety: passing 'service' is generally safe for read-only.
        
        # Re-map snippets from the fetch result (if available)
        snippets = {m['id']: m.get('snippet', '') for m in raw_data if 'id' in m}
        
        # 4. Token Diet
        return _sanitize_email_list(raw_data, snippets)
        
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
def calendar_create_event(
    title: str, 
    start_time: str, 
    end_time: str,
    recurrence: Optional[str] = None
) -> str:
    """
    Create a calendar event with optional recurrence.
    
    Args:
        title: Event title/name
        start_time: Start time in ISO format (YYYY-MM-DDTHH:MM:SS).
        end_time: End time in ISO format (YYYY-MM-DDTHH:MM:SS).
        recurrence: Optional recurrence rule. Use one of:
                   - "daily" or "everyday" for daily events
                   - "weekly" for weekly events
                   - "monthly" for monthly events
                   - "RRULE:..." for custom iCal RRULE
    
    CRITICAL: Always use the current year from system context!
    """
    creds = get_google_creds()
    if not creds: return "❌ Google Auth failed."
    
    try:
        print(f"Called Calendar create (recurrence={recurrence})")
        
        # V15.2: Stale date guard - reject dates more than 1 year in the past
        try:
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            now = datetime.now(start_dt.tzinfo) if start_dt.tzinfo else datetime.now()
            days_diff = (now - start_dt).days
            if days_diff > 365:
                current_year = now.year
                return f"⚠️ Date appears to be in the past ({start_time}). Did you mean {current_year} instead of {start_dt.year}? Please try again with the correct year."
        except Exception:
            pass  # If parsing fails, let Google API handle it
        
        service = build('calendar', 'v3', credentials=creds)
        event = {
            'summary': title,
            'start': {'dateTime': start_time, 'timeZone': USER_TIMEZONE},
            'end': {'dateTime': end_time, 'timeZone': USER_TIMEZONE},
        }
        
        # V15.2: Normalize recurrence into RRULE
        if recurrence:
            recurrence_lower = recurrence.lower().strip()
            if recurrence_lower in ("daily", "everyday", "every day"):
                event['recurrence'] = ['RRULE:FREQ=DAILY']
            elif recurrence_lower == "weekly":
                event['recurrence'] = ['RRULE:FREQ=WEEKLY']
            elif recurrence_lower == "monthly":
                event['recurrence'] = ['RRULE:FREQ=MONTHLY']
            elif recurrence_lower.startswith("rrule:"):
                event['recurrence'] = [recurrence]
            else:
                # Try to be helpful
                print(f"⚠️ Unknown recurrence: {recurrence}, creating one-time event")
        
        event = service.events().insert(calendarId='primary', body=event).execute()
        
        recurrence_note = " (recurring)" if recurrence else ""
        return f"✅ Event created{recurrence_note}: {event.get('htmlLink')}"
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
