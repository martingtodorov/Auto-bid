# Role-local files dir — populated by the operator during initial deploy.
# Real production secrets live here (NEVER committed to git):
#   - frontend.env.production     ← copy from env-templates/frontend.env.production.example
#
# The frontend role does `copy: src: frontend.env.production` which Ansible
# resolves to THIS directory (role_path/files/). If the file is absent, the
# deploy fails with: "Could not find or access 'frontend.env.production'".
#
# First-time setup (run once on the control machine, e.g. your laptop):
#   cd deploy/hetzner/ansible/roles/frontend/files
#   cp ../../../env-templates/frontend.env.production.example frontend.env.production
#   # edit values if needed — for Hetzner the defaults work as-is
#   chmod 600 frontend.env.production
#
# NOTE: the backend role uses a stat-guarded `force: no` copy, so rerunning
# the playbook after the env is deployed will NOT overwrite it. Same for the
# frontend env (see roles/frontend/tasks/main.yml — "Drop production env"
# task).
