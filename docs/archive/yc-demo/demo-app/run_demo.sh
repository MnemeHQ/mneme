#!/usr/bin/env bash
set +e

echo "SCENE 1: AI changes code without Mneme context"
echo "Prompt: Add caching to src/service.py. Use Redis for performance."
echo
cat src/service_bad_ai_output.py

echo
echo "SCENE 2: Run Mneme strict check"
echo "$ python mneme_check_demo.py src/service_bad_ai_output.py"
python mneme_check_demo.py src/service_bad_ai_output.py

echo
echo "SCENE 3: AI changes code with Mneme context"
echo "Prompt: Implement caching again, but follow Mneme's retrieved architectural decisions."
echo
cat src/service_good_mneme_output.py

echo
echo "SCENE 4: Run Mneme strict check again"
echo "$ python mneme_check_demo.py src/service_good_mneme_output.py"
python mneme_check_demo.py src/service_good_mneme_output.py
