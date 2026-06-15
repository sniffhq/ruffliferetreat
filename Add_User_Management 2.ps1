# ============================================================
# Ruff Life Retreat - Add User Management to Admin
# Run as Administrator from C:\RuffLifeRetreat
# ============================================================

$adminRoutes  = "C:\RuffLifeRetreat\app\routes\admin.py"
$templateDir  = "C:\RuffLifeRetreat\app\templates\admin"

# ── 1. Append user management routes to admin.py ────────────

$newRoutes = @'


# ============================================================
# USER MANAGEMENT
# ============================================================

@bp.route('/users')
@login_required
@admin_required
def users():
    """List all users"""
    all_users = User.query.order_by(User.name).all()
    return render_template('admin/users.html', users=all_users)


@bp.route('/users/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_user():
    """Add a new user"""
    if request.method == 'POST':
        name     = request.form.get('name', '').strip()
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()
        role     = request.form.get('role', 'staff')

        if not name or not email or not password:
            flash('Name, email, and password are required.', 'danger')
            return redirect(url_for('admin.add_user'))

        if User.query.filter_by(email=email).first():
            flash('A user with that email already exists.', 'warning')
            return redirect(url_for('admin.add_user'))

        user = User(
            name=name,
            email=email,
            is_admin=(role == 'admin'),
            active=True
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash(f'User {name} created successfully.', 'success')
        return redirect(url_for('admin.users'))

    return render_template('admin/users.html', add_mode=True)


@bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    """Edit a user's name, email, and role"""
    user = User.query.get_or_404(user_id)

    if request.method == 'POST':
        name  = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        role  = request.form.get('role', 'staff')

        if not name or not email:
            flash('Name and email are required.', 'danger')
            return redirect(url_for('admin.edit_user', user_id=user_id))

        existing = User.query.filter_by(email=email).first()
        if existing and existing.id != user.id:
            flash('That email is already in use by another user.', 'warning')
            return redirect(url_for('admin.edit_user', user_id=user_id))

        user.name     = name
        user.email    = email
        user.is_admin = (role == 'admin')
        db.session.commit()
        flash(f'{name} updated successfully.', 'success')
        return redirect(url_for('admin.users'))

    return render_template('admin/users.html', edit_mode=True, edit_user=user)


@bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
@admin_required
def reset_user_password(user_id):
    """Reset a user's password"""
    user     = User.query.get_or_404(user_id)
    password = request.form.get('new_password', '').strip()

    if not password or len(password) < 6:
        flash('Password must be at least 6 characters.', 'danger')
        return redirect(url_for('admin.users'))

    user.set_password(password)
    db.session.commit()
    flash(f'Password for {user.name} has been reset.', 'success')
    return redirect(url_for('admin.users'))


@bp.route('/users/<int:user_id>/toggle-active', methods=['POST'])
@login_required
@admin_required
def toggle_user_active(user_id):
    """Activate or deactivate a user"""
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash('You cannot deactivate your own account.', 'warning')
        return redirect(url_for('admin.users'))

    user.active = not user.active
    db.session.commit()
    status = 'activated' if user.active else 'deactivated'
    flash(f'{user.name} has been {status}.', 'success')
    return redirect(url_for('admin.users'))


@bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    """Permanently delete a user"""
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'warning')
        return redirect(url_for('admin.users'))

    name = user.name
    db.session.delete(user)
    db.session.commit()
    flash(f'{name} has been permanently deleted.', 'danger')
    return redirect(url_for('admin.users'))
'@

Add-Content -Path $adminRoutes -Value $newRoutes
Write-Host "✅ Routes appended to admin.py" -ForegroundColor Green

# ── 2. Create the users.html template ───────────────────────

$template = @'
{% extends "base.html" %}
{% block title %}User Management - Admin{% endblock %}

{% block content %}
<div class="container mt-4">

  {% with messages = get_flashed_messages(with_categories=true) %}
    {% if messages %}
      {% for category, message in messages %}
        <div class="alert alert-{{ category }} alert-dismissible fade show">
          {{ message }}<button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
      {% endfor %}
    {% endif %}
  {% endwith %}

  <!-- ── ADD USER MODAL ── -->
  <div class="modal fade" id="addUserModal" tabindex="-1">
    <div class="modal-dialog">
      <div class="modal-content">
        <div class="modal-header bg-success text-white">
          <h5 class="modal-title"><i class="fas fa-user-plus me-2"></i>Add New User</h5>
          <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
        </div>
        <form method="POST" action="{{ url_for('admin.add_user') }}">
          <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
          <div class="modal-body">
            <div class="mb-3">
              <label class="form-label fw-bold">Full Name</label>
              <input type="text" name="name" class="form-control" required placeholder="Jane Smith">
            </div>
            <div class="mb-3">
              <label class="form-label fw-bold">Email Address</label>
              <input type="email" name="email" class="form-control" required placeholder="jane@example.com">
            </div>
            <div class="mb-3">
              <label class="form-label fw-bold">Temporary Password</label>
              <input type="password" name="password" class="form-control" required minlength="6">
              <div class="form-text">Minimum 6 characters. User should change this after first login.</div>
            </div>
            <div class="mb-3">
              <label class="form-label fw-bold">Role</label>
              <select name="role" class="form-select">
                <option value="staff">Staff</option>
                <option value="admin">Admin</option>
              </select>
            </div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
            <button type="submit" class="btn btn-success"><i class="fas fa-user-plus me-1"></i>Create User</button>
          </div>
        </form>
      </div>
    </div>
  </div>

  <!-- ── EDIT USER MODAL ── -->
  <div class="modal fade" id="editUserModal" tabindex="-1">
    <div class="modal-dialog">
      <div class="modal-content">
        <div class="modal-header bg-primary text-white">
          <h5 class="modal-title"><i class="fas fa-user-edit me-2"></i>Edit User</h5>
          <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
        </div>
        <form method="POST" id="editUserForm" action="">
          <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
          <div class="modal-body">
            <div class="mb-3">
              <label class="form-label fw-bold">Full Name</label>
              <input type="text" name="name" id="editName" class="form-control" required>
            </div>
            <div class="mb-3">
              <label class="form-label fw-bold">Email Address</label>
              <input type="email" name="email" id="editEmail" class="form-control" required>
            </div>
            <div class="mb-3">
              <label class="form-label fw-bold">Role</label>
              <select name="role" id="editRole" class="form-select">
                <option value="staff">Staff</option>
                <option value="admin">Admin</option>
              </select>
            </div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
            <button type="submit" class="btn btn-primary"><i class="fas fa-save me-1"></i>Save Changes</button>
          </div>
        </form>
      </div>
    </div>
  </div>

  <!-- ── RESET PASSWORD MODAL ── -->
  <div class="modal fade" id="resetPwModal" tabindex="-1">
    <div class="modal-dialog">
      <div class="modal-content">
        <div class="modal-header bg-warning text-dark">
          <h5 class="modal-title"><i class="fas fa-key me-2"></i>Reset Password</h5>
          <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
        </div>
        <form method="POST" id="resetPwForm" action="">
          <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
          <div class="modal-body">
            <p>Resetting password for: <strong id="resetPwName"></strong></p>
            <div class="mb-3">
              <label class="form-label fw-bold">New Password</label>
              <input type="password" name="new_password" class="form-control" required minlength="6">
              <div class="form-text">Minimum 6 characters.</div>
            </div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
            <button type="submit" class="btn btn-warning"><i class="fas fa-key me-1"></i>Reset Password</button>
          </div>
        </form>
      </div>
    </div>
  </div>

  <!-- ── PAGE HEADER ── -->
  <div class="d-flex justify-content-between align-items-center mb-4">
    <h2><i class="fas fa-users-cog me-2 text-primary"></i>User Management</h2>
    <div>
      <a href="{{ url_for('admin.dashboard') }}" class="btn btn-secondary me-2">
        <i class="fas fa-arrow-left me-1"></i>Dashboard
      </a>
      <button class="btn btn-success" data-bs-toggle="modal" data-bs-target="#addUserModal">
        <i class="fas fa-user-plus me-1"></i>Add User
      </button>
    </div>
  </div>

  <!-- ── USERS TABLE ── -->
  <div class="card shadow-sm">
    <div class="card-header bg-dark text-white">
      <h5 class="mb-0"><i class="fas fa-list me-2"></i>All Users ({{ users|length }})</h5>
    </div>
    <div class="card-body p-0">
      {% if users %}
      <div class="table-responsive">
        <table class="table table-hover align-middle mb-0">
          <thead class="table-light">
            <tr>
              <th>Name</th>
              <th>Email</th>
              <th>Role</th>
              <th>Status</th>
              <th class="text-center">Actions</th>
            </tr>
          </thead>
          <tbody>
            {% for u in users %}
            <tr class="{{ 'table-secondary text-muted' if not u.active }}">
              <td>
                <i class="fas fa-user-circle me-2 text-secondary"></i>{{ u.name }}
                {% if u.id == current_user.id %}
                  <span class="badge bg-info ms-1">You</span>
                {% endif %}
              </td>
              <td>{{ u.email }}</td>
              <td>
                {% if u.is_admin %}
                  <span class="badge bg-danger">Admin</span>
                {% else %}
                  <span class="badge bg-secondary">Staff</span>
                {% endif %}
              </td>
              <td>
                {% if u.active %}
                  <span class="badge bg-success">Active</span>
                {% else %}
                  <span class="badge bg-secondary">Inactive</span>
                {% endif %}
              </td>
              <td class="text-center">
                <div class="btn-group btn-group-sm">

                  <!-- Edit -->
                  <button class="btn btn-outline-primary"
                    onclick="openEditModal({{ u.id }}, '{{ u.name|e }}', '{{ u.email|e }}', '{{ 'admin' if u.is_admin else 'staff' }}')"
                    title="Edit User">
                    <i class="fas fa-edit"></i>
                  </button>

                  <!-- Reset Password -->
                  <button class="btn btn-outline-warning"
                    onclick="openResetModal({{ u.id }}, '{{ u.name|e }}')"
                    title="Reset Password">
                    <i class="fas fa-key"></i>
                  </button>

                  <!-- Toggle Active (can't deactivate yourself) -->
                  {% if u.id != current_user.id %}
                  <form method="POST" action="{{ url_for('admin.toggle_user_active', user_id=u.id) }}" class="d-inline">
                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                    <button type="submit" class="btn {{ 'btn-outline-secondary' if u.active else 'btn-outline-success' }}"
                      title="{{ 'Deactivate' if u.active else 'Activate' }}"
                      onclick="return confirm('{{ 'Deactivate' if u.active else 'Activate' }} {{ u.name }}?')">
                      <i class="fas {{ 'fa-user-slash' if u.active else 'fa-user-check' }}"></i>
                    </button>
                  </form>

                  <!-- Delete -->
                  <form method="POST" action="{{ url_for('admin.delete_user', user_id=u.id) }}" class="d-inline">
                    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
                    <button type="submit" class="btn btn-outline-danger"
                      title="Delete Permanently"
                      onclick="return confirm('Permanently delete {{ u.name }}? This cannot be undone.')">
                      <i class="fas fa-trash"></i>
                    </button>
                  </form>
                  {% endif %}

                </div>
              </td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
      {% else %}
        <div class="text-center py-5 text-muted">
          <i class="fas fa-users fa-3x mb-3"></i>
          <p>No users found. Add one above.</p>
        </div>
      {% endif %}
    </div>
  </div>
</div>

<script>
function openEditModal(id, name, email, role) {
  document.getElementById('editName').value  = name;
  document.getElementById('editEmail').value = email;
  document.getElementById('editRole').value  = role;
  document.getElementById('editUserForm').action = '/admin/users/' + id + '/edit';
  new bootstrap.Modal(document.getElementById('editUserModal')).show();
}

function openResetModal(id, name) {
  document.getElementById('resetPwName').textContent = name;
  document.getElementById('resetPwForm').action = '/admin/users/' + id + '/reset-password';
  new bootstrap.Modal(document.getElementById('resetPwModal')).show();
}
</script>
{% endblock %}
'@

$templatePath = Join-Path $templateDir "users.html"
Set-Content -Path $templatePath -Value $template -Encoding UTF8
Write-Host "✅ Template created at $templatePath" -ForegroundColor Green

# ── 3. Verify the dashboard has a link to /admin/users ──────

$dashboardPath = Join-Path $templateDir "dashboard.html"
$dashContent   = Get-Content $dashboardPath -Raw

if ($dashContent -notmatch "admin\.users") {
    Write-Host ""
    Write-Host "⚠️  No link to User Management found in dashboard.html." -ForegroundColor Yellow
    Write-Host "    Add this somewhere in your admin nav or dashboard cards:" -ForegroundColor Yellow
    Write-Host "    <a href=`"{{ url_for('admin.users') }}`" class=`"btn btn-primary`">User Management</a>" -ForegroundColor Cyan
} else {
    Write-Host "✅ Dashboard already links to User Management." -ForegroundColor Green
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host " User Management setup complete!" -ForegroundColor Cyan
Write-Host " Navigate to: /admin/users" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Restart Flask to apply changes." -ForegroundColor Yellow