from flask import (
    Blueprint, render_template, session
)
from stkikp_nk.auth import login_required

bp = Blueprint('other', __name__)

def delete_saved_input_threshold():
    if session.get('input'):
        session.pop('input')
    if session.get('threshold'):
        session.pop('threshold')

@bp.route('/about')
@login_required
def about():
    delete_saved_input_threshold()
    return render_template('main/about.html')