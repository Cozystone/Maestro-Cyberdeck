@echo off
chcp 65001 >nul
title ATANOR
ssh -t -i "%LOCALAPPDATA%\atanor-tunnel\admin_ed25519" -o IdentitiesOnly=yes -o UserKnownHostsFile="%LOCALAPPDATA%\atanor-tunnel\known_hosts" -o StrictHostKeyChecking=yes mind@192.168.0.149 atanor %*
