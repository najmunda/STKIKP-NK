from flask import (
    Blueprint, render_template
)
from NLPCBR.auth import login_required

bp = Blueprint('other', __name__)

@bp.route('/about')
@login_required
def about():
    return render_template('main/about.html')