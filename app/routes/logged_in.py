# app\routes\logged_in.py: Stores all the routes that a logged in user can view
from . import *

# Define blueprint for main routes
bp = Blueprint('logged_in', __name__)

# Route for the dashboard page when the user is logged in
@bp.route('/visualise/', methods=['GET', 'POST'])
@login_required
def home_logged_in():
    if not current_user.is_authenticated:
        return redirect(url_for('logged_out.login'))  # Redirect to login if not logged in
    
    form = LogoutForm()  # Create an instance of the form
    if form.validate_on_submit():
        logout_user()  # Call Flask-Login's logout function to log out the user
        return redirect(url_for('logged_out.home_not_logged_in'))  # Redirect to the home page
    
    return render_template('user/dashboard.html', form=form)  # Pass the form to the template

# Route for the share page
@bp.route('/share/')
@login_required
def share():
    return render_template('user/share.html')

# API endpoint for user search by email
@bp.route('/api/users/search', methods=['GET'])
@login_required
def search_users():
    """Search users by email (partial match)"""
    query = request.args.get('query', '')
    if len(query) < 3:
        return jsonify([]), 200
    
    # Search for users with email containing the query string
    users = User.query.filter(
        User.email.like(f'%{query}%'),
        User.id != current_user.id  # Exclude current user
    ).limit(10).all()
    
    return jsonify([{
        'id': user.id,
        'email': user.email
    } for user in users]), 200

# API endpoint for sharing data with another user
@bp.route('/api/share', methods=['POST'])
@login_required
def share_data():
    """Share data with another user"""
    data = request.get_json()
    recipient_id = data.get('recipient_id')
    session_id = data.get('session_id') or 1
    shared_content = data.get('shared_content', 20)
    shared_content3 = data.get('shared_content3', 'YOU RECEIVE A SHARE')

    if not recipient_id or not session_id:
        flash('Recipient ID and session ID are required', 'error')
        return jsonify({'error': 'Recipient ID and session ID are required'}), 400

    # check recipient
    recipient = db.session.get(User, recipient_id)
    if not recipient:
        flash('Recipient not found', 'error')
        return jsonify({'error': 'Recipient not found'}), 404
    
    shared_data = SharedData(
        session_id=session_id,
        shared_by_user_id=current_user.id,
        shared_with_user_id=recipient_id,
        shared_content=shared_content,
        shared_content3=shared_content3,
        status='pending'
    )

    try:
        db.session.add(shared_data)
        db.session.commit()
        flash(f'Data shared with {recipient.email}', 'success')
        return jsonify({'success': True, 'message': f'Data shared with {recipient.email}'}), 201
    except Exception as e:
        db.session.rollback()
        flash(f'Error sharing data: {str(e)}', 'error')
        return jsonify({'error': str(e)}), 500

# API endpoint for getting received shares
@bp.route('/api/shares/received', methods=['GET'])
@login_required
def get_received_shares():
    """Get all shares received by the current user"""
    shares = SharedData.query.filter_by(
        shared_with_user_id=current_user.id
    ).order_by(SharedData.shared_on.desc()).all()
    
    return jsonify([{
        'id': share.id,
        'shared_by': share.shared_by_user.email,
        'shared_content': share.shared_content,
        'shared_content3': share.shared_content3,
        'shared_on': share.shared_on.isoformat(),
        'status': share.status
    } for share in shares]), 200

# API endpoint for accepting a share
@bp.route('/api/shares/accept/<int:share_id>', methods=['POST'])
@login_required
def accept_share(share_id):
    """Accept a shared data item"""
    share = SharedData.query.get_or_404(share_id)
    
    # Verify the share is for the current user
    if share.shared_with_user_id != current_user.id:
        flash('Unauthorized access', 'error')
        return jsonify({'error': 'Unauthorized'}), 403
    
    share.status = 'accepted'
    
    try:
        db.session.commit()
        flash('Share accepted successfully', 'success')
        return jsonify({
            'success': True,
            'message': 'Share accepted'
        }), 200
    except Exception as e:
        db.session.rollback()
        flash(f'Error accepting share: {str(e)}', 'error')
        return jsonify({'error': str(e)}), 500

@bp.route('/api/study-distribution')
@login_required
def study_distribution():
    """
    Returns study minutes per weekday for the current week (Mon-Sun).
    Output: [{"day": "Monday", "minutes": 120}, ...]
    """
    from app.models.session import Session
    from datetime import datetime, timedelta

    today = datetime.today().date()
    # Find this week's Monday
    monday = today - timedelta(days=today.weekday())
    week_days = [monday + timedelta(days=i) for i in range(7)]
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    # Query all sessions for this week
    sessions = Session.query.filter(
        Session.user_id == current_user.id,
        Session.date >= monday,
        Session.date <= monday + timedelta(days=6)
    ).all()

    # Aggregate minutes per day
    minutes_per_day = {d: 0 for d in day_names}
    for s in sessions:
        idx = (s.date - monday).days
        if 0 <= idx < 7:
            start = s.start_time
            end = s.end_time
            duration = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute) - (s.break_minutes or 0)
            minutes_per_day[day_names[idx]] += max(duration, 0)

    result = [{"day": d, "minutes": minutes_per_day[d]} for d in day_names]
    return jsonify(result)

@bp.route('/api/study-streak', methods=['GET', 'POST'])
@login_required
def study_streak():
    """
    GET: Returns current streak, longest streak, and freeze info.
    POST: Use a streak freeze if available.
    """
    from app.models.session import Session
    from app.models.streak_freeze import StreakFreeze  # You may need to create this model

    today = datetime.today().date()
    sessions = Session.query.filter_by(user_id=current_user.id).order_by(Session.date.desc()).all()
    dates = set(s.date for s in sessions)

    # Calculate current streak
    streak = 0
    day = today
    while day in dates:
        streak += 1
        day -= timedelta(days=1)

    # Calculate longest streak
    longest = 0
    temp = 0
    prev = None
    for d in sorted(dates, reverse=True):
        if prev is None or prev - timedelta(days=1) == d:
            temp += 1
        else:
            longest = max(longest, temp)
            temp = 1
        prev = d
    longest = max(longest, temp)

    # Streak freeze logic (1 per month)
    freeze_this_month = StreakFreeze.query.filter_by(user_id=current_user.id, month=today.month, year=today.year).first()
    freeze_available = freeze_this_month is None

    if request.method == 'POST':
        # Use a freeze if available and streak was broken yesterday and today is also missed
        yesterday = today - timedelta(days=1)
        if freeze_available and yesterday not in dates and today not in dates:
            # Grant freeze
            new_freeze = StreakFreeze(user_id=current_user.id, month=today.month, year=today.year, used_on=today)
            db.session.add(new_freeze)
            db.session.commit()
            return jsonify({"success": True, "message": "Streak freeze used!"})
        else:
            return jsonify({"success": False, "message": "No freeze available or not eligible."}), 400

    return jsonify({
        "current_streak": streak,
        "longest_streak": longest,
        "freeze_available": freeze_available
    })

@bp.route('/api/reflections', methods=['GET', 'POST'])
@login_required
def reflections():
    if request.method == 'GET':
        reflections = Reflection.query.filter_by(user_id=current_user.id).order_by(Reflection.created_at.desc()).limit(10).all()
        return jsonify([
            {
                "id": r.id,
                "content": r.content,
                "mood": r.mood,
                "tags": r.tags,
                "created_at": r.created_at.isoformat()  # includes timezone info if aware
            } for r in reflections
        ])
    elif request.method == 'POST':
        data = request.get_json()
        content = data.get('content', '').strip()
        mood = data.get('mood')
        tags = data.get('tags')
        if not content:
            return jsonify({"error": "Reflection cannot be empty."}), 400
        reflection = Reflection(user_id=current_user.id, content=content, mood=mood, tags=tags)
        db.session.add(reflection)
        db.session.commit()
        return jsonify({"success": True, "id": reflection.id})

@bp.route('/api/reflections/<int:reflection_id>', methods=['PUT', 'DELETE'])
@login_required
def reflection_detail(reflection_id):
    reflection = Reflection.query.get_or_404(reflection_id)
    if reflection.user_id != current_user.id:
        return jsonify({"error": "Unauthorized"}), 403
    if request.method == 'PUT':
        data = request.get_json()
        reflection.content = data.get('content', reflection.content)
        reflection.mood = data.get('mood', reflection.mood)
        reflection.tags = data.get('tags', reflection.tags)
        db.session.commit()
        return jsonify({"success": True})
    elif request.method == 'DELETE':
        db.session.delete(reflection)
        db.session.commit()
        return jsonify({"success": True})

@bp.route('/api/course-insights')
@login_required
def course_insights():
    # Support ?range=week|month|overall
    from sqlalchemy import func
    from datetime import datetime, timedelta

    range_type = request.args.get('range', 'week')
    today = datetime.today().date()
    if range_type == "week":
        cutoff = today - timedelta(days=6)
    elif range_type == "month":
        cutoff = today - timedelta(days=29)
    elif range_type == "overall":
        cutoff = None
    else:
        cutoff = today - timedelta(days=6)

    query = Session.query.filter(Session.user_id == current_user.id)
    if cutoff:
        query = query.filter(Session.date >= cutoff)
    sessions = query.all()

    course_stats = {}
    for s in sessions:
        c = s.course
        if c not in course_stats:
            course_stats[c] = {"total_minutes": 0, "total_productivity": 0, "session_count": 0}
        start = s.start_time
        end = s.end_time
        duration = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute) - (s.break_minutes or 0)
        course_stats[c]["total_minutes"] += max(duration, 0)
        course_stats[c]["total_productivity"] += s.productivity_rating
        course_stats[c]["session_count"] += 1

    result = []
    for c, stats in course_stats.items():
        avg_prod = stats["total_productivity"] / stats["session_count"] if stats["session_count"] else 0
        result.append({
            "course": c,
            "total_minutes": stats["total_minutes"],
            "avg_productivity": round(avg_prod, 2),
            "session_count": stats["session_count"]
        })
    return jsonify(result)

@bp.route('/api/sessions', methods=['GET', 'POST'])
@login_required
def api_sessions():
    """Get all sessions or create a new session"""
    if request.method == 'GET':
        try:
            sessions = Session.query.filter_by(user_id=current_user.id).all()
            session_list = []
            
            for session in sessions:
                # Calculate duration from start and end time
                start = session.start_time
                end = session.end_time
                duration_minutes = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute) - (session.break_minutes)
                hours = duration_minutes // 60
                minutes = duration_minutes % 60
                duration = f"{hours}h {minutes}m"
                
                # Format time as "start_time - end_time"
                time_range = f"{start.strftime('%H:%M')} - {end.strftime('%H:%M')}"
                
                # Format date as DD/MM/YYYY to match frontend display
                formatted_date = session.date.strftime('%d/%m/%Y')
                
                session_list.append({
                    "session_id": session.session_id,  # Standardized to session_id
                    "date": formatted_date,
                    "time": time_range, 
                    "duration": duration,
                    "break_minutes": session.break_minutes,
                    "course": session.course,
                    "productivity": session.productivity_rating,
                    "notes": session.notes
                })
                
            return jsonify(session_list), 200
        except Exception as e:
            return jsonify({'error': 'Failed to fetch sessions'}), 500

    elif request.method == 'POST':
        session_data = request.get_json()
        
        # Validate the session data directly with standardized field names
        validated_data = validate_session_data(session_data)
        if 'error' in validated_data:
            return jsonify(validated_data), 400

        try:
            new_session = Session(
                user_id=current_user.id,
                date=validated_data['date'],
                start_time=validated_data['start_time'],
                end_time=validated_data['end_time'],
                break_minutes=int(session_data['break_minutes']) if session_data.get('break_minutes') else None,
                course=session_data['course'],
                productivity_rating=int(session_data['productivity']),
                notes=session_data.get('notes')
            )

            db.session.add(new_session)
            db.session.commit()

            return jsonify({'message': 'Session added successfully', 'session_id': new_session.session_id}), 201
        
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 400

@bp.route('/api/sessions/<int:session_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def session_detail(session_id):
    """Get, update or delete a specific session"""
    # First, get the session and check permissions
    session = Session.query.get_or_404(session_id)
    if session.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    if request.method == 'GET':
        # Return the session details
        start = session.start_time
        end = session.end_time
        duration_minutes = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute) - (session.break_minutes)
        hours = duration_minutes // 60
        minutes = duration_minutes % 60
        
        session_data = {
            "session_id": session.session_id,
            "date": session.date.strftime('%Y-%m-%d'),
            "start_time": start.strftime('%H:%M'),
            "end_time": end.strftime('%H:%M'),
            "duration": f"{hours}h {minutes}m",
            "break_minutes": session.break_minutes,
            "course": session.course,
            "productivity": session.productivity_rating,
            "notes": session.notes
        }
        
        return jsonify(session_data), 200
        
    elif request.method == 'PUT':
        # Update the session
        session_data = request.get_json()
        
        # Validate the session data
        validated_data = validate_session_data(session_data)
        if 'error' in validated_data:
            return jsonify(validated_data), 400
            
        try:
            # Update session fields
            session.date = validated_data['date']
            session.start_time = validated_data['start_time']
            session.end_time = validated_data['end_time']
            session.break_minutes = int(session_data['break_minutes']) if session_data.get('break_minutes') else None
            session.course = session_data['course']
            session.productivity_rating = int(session_data['productivity'])
            session.notes = session_data.get('notes')
            
            db.session.commit()
            return jsonify({'message': 'Session updated successfully'}), 200
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 400
    
    elif request.method == 'DELETE':
        try:
            db.session.delete(session)
            db.session.commit()
            return jsonify({'message': 'Session deleted successfully'}), 200
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

@bp.route('/api/sessions/bulk-delete', methods=['POST'])
@login_required
def bulk_delete_sessions():
    """Delete multiple sessions at once"""
    try:
        # Ensure the request is JSON
        if not request.is_json:
            return jsonify({'error': 'Request must be JSON'}), 400
            
        data = request.get_json()
        
        # Only accept session_ids as the parameter name
        if 'session_ids' not in data:
            return jsonify({'error': 'session_ids field is required'}), 400
            
        session_ids = data['session_ids']
        
        # Validate that session_ids is a list of integers
        if not isinstance(session_ids, list):
            return jsonify({'error': 'session_ids must be a list'}), 400
            
        # Convert any string IDs to integers
        try:
            session_ids = [int(id) for id in session_ids]
        except ValueError:
            return jsonify({'error': 'All session IDs must be integers'}), 400
            
        # Check if these sessions exist for this user
        existing_sessions = Session.query.filter(
            Session.session_id.in_(session_ids),
            Session.user_id == current_user.id
        ).all()
        
        existing_ids = [s.session_id for s in existing_sessions]
        
        if not existing_ids:
            return jsonify({'message': 'No matching sessions found to delete'}), 200
            
        # Delete the sessions
        deletion_count = 0
        for session in existing_sessions:
            db.session.delete(session)
            deletion_count += 1
        
        # Commit all successful deletions
        db.session.commit()
        return jsonify({'message': f'{deletion_count} sessions deleted successfully'}), 200
            
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Server error: {str(e)}'}), 500

def validate_session_data(session_data):
    try:
        # Check for required fields using standardised names
        date_field = session_data.get('date')
        start_field = session_data.get('start_time')
        end_field = session_data.get('end_time')
        course = session_data.get('course')
        notes = session_data.get('notes')

        # Check if required fields exist
        if not date_field or not start_field or not end_field or not course or not notes:
            return {'error': 'Required fields (date, start_time, end_time, course, notes) are missing'}

        # Parse date and times
        session_date = datetime.strptime(date_field, '%Y-%m-%d').date()
        start_time = datetime.strptime(start_field, '%H:%M').time()
        end_time = datetime.strptime(end_field, '%H:%M').time()
    
        # Check if end time is after start time
        if (datetime.combine(datetime.today(), end_time) <= datetime.combine(datetime.today(), start_time)):
            return {'error': 'End time must be after start time'}
        if len(course) >= 10:
            return {'error': 'Course name must be 9 characters or fewer'}
        if len(notes) >= 26:
            return {'error': 'Notes must be 25 characters or fewer'}
        
        return {
            'date': session_date,
            'start_time': start_time,
            'end_time': end_time,
            'notes': notes,
            'course': course,
        }
    except ValueError as e:
        return {'error': f'Invalid date or time format: {str(e)}'}
    except Exception as e:
        return {'error': f'Validation error: {str(e)}'}

@bp.route('/api/productivity-trend')
@login_required
def productivity_trend():
    # Get range from query param
    range_type = request.args.get('range', 'week')
    today = datetime.today().date()
    if range_type == 'day':
        days = [today]
    elif range_type == 'month':
        days = [today - timedelta(days=i) for i in range(29, -1, -1)]
    else:  # default to week
        days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    data = []
    for day in days:
        sessions = Session.query.filter_by(user_id=current_user.id, date=day).all()
        total_minutes = sum(
            max((s.end_time.hour*60 + s.end_time.minute) - (s.start_time.hour*60 + s.start_time.minute) - (s.break_minutes or 0), 0)
            for s in sessions
        )
        avg_productivity = (
            sum(s.productivity_rating for s in sessions) / len(sessions)
            if sessions else 0
        )
        data.append({
            "date": day.strftime('%Y-%m-%d'),
            "study_minutes": total_minutes,
            "avg_productivity": avg_productivity * 10  # as percent
        })
    return jsonify(data)

@bp.route('/api/user-stats')
@login_required
def user_stats():
    today = datetime.today().date()
    yesterday = today - timedelta(days=1)
    week_start = today - timedelta(days=6)
    prev_week_start = week_start - timedelta(days=7)
    prev_week_end = week_start - timedelta(days=1)

    # Helper for durations
    def get_total_duration(sessions):
        total = 0
        for s in sessions:
            start = s.start_time
            end = s.end_time
            duration = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute) - (s.break_minutes or 0)
            total += max(duration, 0)
        return total

    # Today & Yesterday
    today_sessions = Session.query.filter_by(user_id=current_user.id, date=today).all()
    yesterday_sessions = Session.query.filter_by(user_id=current_user.id, date=yesterday).all()
    today_minutes = get_total_duration(today_sessions)
    yesterday_minutes = get_total_duration(yesterday_sessions)
    today_delta = (
        ((today_minutes - yesterday_minutes) / yesterday_minutes * 100) if yesterday_minutes else None
    )

    # Trailing week & previous week
    week_sessions = Session.query.filter(
        Session.user_id == current_user.id,
        Session.date >= week_start,
        Session.date <= today
    ).all()
    prev_week_sessions = Session.query.filter(
        Session.user_id == current_user.id,
        Session.date >= prev_week_start,
        Session.date <= prev_week_end
    ).all()

    # Sessions count
    week_count = len(week_sessions)
    prev_week_count = len(prev_week_sessions)
    sessions_delta = (
        ((week_count - prev_week_count) / prev_week_count * 100) if prev_week_count else None
    )

    # Avg duration
    week_avg = (get_total_duration(week_sessions) / week_count) if week_count else 0
    prev_week_avg = (get_total_duration(prev_week_sessions) / prev_week_count) if prev_week_count else 0
    avg_duration_delta = (
        ((week_avg - prev_week_avg) / prev_week_avg * 100) if prev_week_avg else None
    )

    # Avg productivity
    week_prod = (
        sum(s.productivity_rating for s in week_sessions) / week_count if week_count else 0
    )
    prev_week_prod = (
        sum(s.productivity_rating for s in prev_week_sessions) / prev_week_count if prev_week_count else 0
    )
    # Normalize to percentage (scale 1-10 becomes 10-100%)
    week_prod_pct = week_prod * 10
    prev_week_prod_pct = prev_week_prod * 10
    avg_prod_delta = (
        ((week_prod_pct - prev_week_prod_pct) / prev_week_prod_pct * 100) if prev_week_prod_pct else None
    )

    # This week total
    week_total_minutes = get_total_duration(week_sessions)
    prev_week_total_minutes = get_total_duration(prev_week_sessions)
    week_total_delta = (
        ((week_total_minutes - prev_week_total_minutes) / prev_week_total_minutes * 100) if prev_week_total_minutes else None
    )

    def format_minutes(minutes):
        h = minutes // 60
        m = minutes % 60
        return f"{h}h {m}m" if h else f"{m}m"

    def format_delta(delta):
        if delta is None:
            return {"delta": "-", "deltaType": "neutral"}
        elif delta > 0:
            return {"delta": f"+{round(delta)}%", "deltaType": "positive"}
        elif delta < 0:
            return {"delta": f"{round(delta)}%", "deltaType": "negative"}
        else:
            return {"delta": "-", "deltaType": "neutral"}

    return jsonify([
        {
            "label": "Today",
            "icon": "clock",
            "value": format_minutes(today_minutes),
            **format_delta(today_delta),
            "bgColor": "bg-blue-50",
            "iconColor": "text-blue-500",
            "textColor": "text-blue-800",
        },
        {
            "label": "Sessions",
            "icon": "play-circle",
            "value": str(week_count),
            **format_delta(sessions_delta),
            "bgColor": "bg-green-50",
            "iconColor": "text-green-500",
            "textColor": "text-green-800",
        },
        {
            "label": "Avg. Duration",
            "icon": "timer",
            "value": format_minutes(int(week_avg)),
            **format_delta(avg_duration_delta),
            "bgColor": "bg-yellow-50",
            "iconColor": "text-yellow-500",
            "textColor": "text-yellow-800",
        },
        {
            "label": "Avg. Productivity",
            "icon": "activity",
            "value": f"{round(week_prod_pct)}%",
            **format_delta(avg_prod_delta),
            "bgColor": "bg-purple-50",
            "iconColor": "text-purple-500",
            "textColor": "text-purple-800",
        },
        {
            "label": "This Week",
            "icon": "calendar-days",
            "value": format_minutes(week_total_minutes),
            **format_delta(week_total_delta),
            "bgColor": "bg-red-50",
            "iconColor": "text-red-500",
            "textColor": "text-red-800",
        },
    ])

@bp.route('/upload/', methods=['GET', 'POST'])
@login_required
def upload_data():
    if request.method == 'POST':
        # Check if a CSV file was uploaded
        if 'data_file' in request.files and request.files['data_file'].filename != '':
            file = request.files['data_file']
            if not file.filename.endswith('.csv'):
                flash("Please upload a CSV file.", "error")
                return redirect(url_for("logged_in.upload_data"))

            try:
                # Read and decode the CSV file
                reader = csv.DictReader(TextIOWrapper(file, encoding='utf-8'))
                added, errors = 0, []
                for idx, row in enumerate(reader, start=1):
                    # Map CSV columns to standardized field names
                    session_data = {
                        'date': row.get('date'),
                        'start_time': row.get('start'),
                        'end_time': row.get('end'),
                        'break_minutes': row.get('break', 0),
                        'course': row.get('subject'),
                        'productivity': row.get('rating'),
                        'notes': row.get('activity')
                    }
                    validated = validate_session_data(session_data)
                    if 'error' in validated:
                        errors.append(f"Row {idx}: {validated['error']}")
                        continue

                    try:
                        new_session = Session(
                            user_id=current_user.id,
                            date=validated['date'],
                            start_time=validated['start_time'],
                            end_time=validated['end_time'],
                            break_minutes=int(session_data['break_minutes']) if session_data.get('break_minutes') else None,
                            course=session_data['course'],
                            productivity_rating=int(session_data['productivity']),
                            notes=session_data.get('notes')
                        )
                        db.session.add(new_session)
                        added += 1
                    except Exception as e:
                        errors.append(f"Row {idx}: {str(e)}")
                db.session.commit()
                msg = f"{added} sessions uploaded successfully."
                if errors:
                    msg += " Some rows failed: " + "; ".join(errors)
                flash(msg if added else "Error uploading sessions.", 'success' if added else 'error')
                return redirect(url_for('logged_in.upload_data'))

            except Exception as e:
                db.session.rollback()
                flash(f"Error processing CSV: {str(e)}", "error")
                return redirect(url_for("logged_in.upload_data"))
        else:
            # Manual form entry
            form_data = request.form.to_dict()
            
            # Check for flash message from frontend validation
            if 'flash_message' in form_data:
                flash(form_data['flash_message'], "error")
                return redirect(url_for("logged_in.upload_data"))

            session_data = {
                'date': form_data.get('date'),
                'start_time': form_data.get('start_time'),
                'end_time': form_data.get('end_time'),
                'break_minutes': form_data.get('break_minutes'),
                'course': form_data.get('course'),
                'productivity': form_data.get('productivity'),
                'notes': form_data.get('notes')
            }
            validated_data = validate_session_data(session_data)
            if 'error' in validated_data:
                flash(validated_data['error'], "error")
                return redirect(url_for("logged_in.upload_data"))

            try:
                new_session = Session(
                    user_id=current_user.id,
                    date=validated_data['date'],
                    start_time=validated_data['start_time'],
                    end_time=validated_data['end_time'],
                    break_minutes=int(session_data['break_minutes']) if session_data.get('break_minutes') else None,
                    course=session_data['course'],
                    productivity_rating=int(session_data['productivity']),
                    notes=session_data.get('notes')
                )
                db.session.add(new_session)
                db.session.commit()
                flash("Session successfully added!", "success")
                return redirect(url_for("logged_in.upload_data"))
            except Exception as e:
                db.session.rollback()
                flash(f"Error: {str(e)}", "error")
                return redirect(url_for("logged_in.upload_data"))

    # GET Request - Retrieve all sessions for the current user
    sessions = Session.query.filter_by(user_id=current_user.id).all()

    # Pass the sessions to the template for display
    return render_template('user/upload.html', sessions=sessions)

@bp.route('/dashboard/')
@login_required
def dashboard():
    return render_template('user/dashboard.html')

# API route to return study time data as JSON
@bp.route('/api/total-study-time')
@login_required
def total_study_time():
    """Calculate total study time from all sessions"""
    sessions = Session.query.filter_by(user_id=current_user.id).all()
    
    total_minutes = 0
    for s in sessions:
        start = s.start_time
        end = s.end_time
        duration = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute) - (s.break_minutes or 0)
        total_minutes += max(duration, 0)
    
    hours = total_minutes // 60
    minutes = total_minutes % 60
    
    return jsonify({
        "hours": hours,
        "minutes": minutes
    })

@bp.route('/api/study-time-data')
@login_required
def study_time_data():
    data = [
        {"date": "2025-04-01", "studyTime": 2},
        {"date": "2025-04-02", "studyTime": 3},
        {"date": "2025-04-03", "studyTime": 1.5},
    ]
    return jsonify(data)

@bp.route('/profile/remove_friend/<int:friend_id>', methods=['POST'], endpoint='logged_in_remove_friend')
@login_required
def remove_friend(friend_id):
    # Get the friend from the database
    friend = User.query.get_or_404(friend_id)
    
    # Remove each other from their friend lists
    if friend in current_user.friends:
        current_user.friends.remove(friend)
    if current_user in friend.friends:
        friend.friends.remove(current_user)
    
    # Commit the changes to the database
    db.session.commit()
    
    flash('Friend removed successfully!', 'success')
    return redirect(url_for('logged_in.profile'))

@bp.route('/profile/', methods=['GET', 'POST'])
@login_required
def profile():
    form = AddFriendForm()

    if form.validate_on_submit():
        friend_email = form.email.data
        friend = User.query.filter_by(email=friend_email).first()

        if friend:
            if friend.id != current_user.id:
                add_friend(friend)
                flash('Friend added successfully!', 'success')
            else:
                flash('You cannot add yourself as a friend.', 'warning')
        else:
            flash('User not found.', 'error')

        return redirect(url_for('logged_in.profile'))

    all_friends = current_user.friends  # this is now safe
    return render_template('user/profile.html', form=form, all_friends=all_friends)

def add_friend(user_to_add):
    if not current_user.friends.filter_by(id=user_to_add.id).first():
        current_user.friends.append(user_to_add)
    if not user_to_add.friends.filter_by(id=current_user.id).first():
        user_to_add.friends.append(current_user)
    db.session.commit()

@bp.route('/api/friends/add', methods=['POST'])
@login_required
def api_add_friend():
    data = request.get_json()
    friend_email = data.get('email')
    
    if not friend_email:
        return jsonify({'error': 'Email is required'}), 400
        
    friend = User.query.filter_by(email=friend_email).first()
    
    if not friend:
        return jsonify({'error': 'User not found'}), 404
        
    if friend.id == current_user.id:
        return jsonify({'error': 'You cannot add yourself as a friend'}), 400
        
    # Check if already friends
    if current_user.friends.filter_by(id=friend.id).first():
        return jsonify({'error': 'Already friends with this user'}), 400
        
    try:
        add_friend(friend)
        return jsonify({
            'success': True,
            'message': 'Friend added successfully',
            'friend': {
                'id': friend.id,
                'email': friend.email
            }
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/api/friends/remove/<int:friend_id>', methods=['POST'])
@login_required
def api_remove_friend(friend_id):
    friend = User.query.get_or_404(friend_id)
    
    if friend not in current_user.friends:
        return jsonify({'error': 'Not friends with this user'}), 400
        
    try:
        if friend in current_user.friends:
            current_user.friends.remove(friend)
        if current_user in friend.friends:
            friend.friends.remove(current_user)
        
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Friend removed successfully'
        }), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@bp.route('/api/friends', methods=['GET'])
@login_required
def api_get_friends():
    friends = current_user.friends.all()
    return jsonify([{
        'id': friend.id,
        'email': friend.email
    } for friend in friends]), 200
