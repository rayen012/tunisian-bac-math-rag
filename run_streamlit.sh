#!/bin/bash
# ──────────────────────────────────────────────
# Run Streamlit accessible through JupyterLab proxy
# ──────────────────────────────────────────────
#
# On Vertex AI Workbench, port 8501 is firewalled.
# But JupyterLab's proxy at /proxy/8501/ is already authenticated.
#
# After running this script, access Streamlit at:
#   https://<your-workbench-url>/proxy/8501/
#
# You can find your workbench URL in the Vertex AI console
# or by running: gcloud workbench instances describe <name> --location=<zone>
#
# Usage:
#   chmod +x run_streamlit.sh
#   ./run_streamlit.sh

set -e

cd "$(dirname "$0")"

echo "=========================================="
echo "  Starting Streamlit for Workbench proxy"
echo "=========================================="
echo ""
echo "Once started, access the app at:"
echo "  https://<your-workbench-url>/proxy/8501/"
echo ""
echo "Find your workbench URL in the GCP console under:"
echo "  Vertex AI → Workbench → Instances → OPEN JUPYTERLAB"
echo "  Then replace /lab with /proxy/8501/"
echo ""
echo "=========================================="
echo ""

python -m streamlit run app.py \
    --server.port 8501 \
    --server.address 0.0.0.0 \
    --server.headless true \
    --server.enableCORS false \
    --server.enableXsrfProtection false \
    --browser.gatherUsageStats false
