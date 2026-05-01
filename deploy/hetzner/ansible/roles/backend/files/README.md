# Role-local files dir — populated by the operator during initial deploy.
# Real production secrets live here (NEVER committed to git):
#   - backend.env               ← copy from env-templates/backend.env.example
#
# The backend role does `copy: src: backend.env` which Ansible resolves to
# THIS directory (role_path/files/). If the file is absent, the deploy fails
# with: "Could not find or access 'backend.env'".
#
# First-time setup (run once on the control machine, e.g. your laptop):
#   cd deploy/hetzner/ansible/roles/backend/files
#   cp ../../../env-templates/backend.env.example backend.env
#   # fill in real values — JWT_SECRET, STRIPE_API_KEY, RESEND_API_KEY,
#   # VAPID_PUBLIC_KEY / _PRIVATE_KEY, GEMINI_API_KEY, ADMIN_PASSWORD, etc.
#   chmod 600 backend.env
#
# IMPORTANT: the backend role uses a stat-guarded `force: no` copy, so
# rerunning the playbook after backend.env is deployed will NOT overwrite
# the live production file. To rotate a secret, edit /etc/autobids/backend.env
# directly on the server and restart the service.
