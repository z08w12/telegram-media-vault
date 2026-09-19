# Security Policy

## Reporting a vulnerability

Please do not disclose security vulnerabilities in a public issue.

Use GitHub's **Private vulnerability reporting** feature on the repository's
Security tab. Include the affected version, reproduction steps, expected
impact, and any suggested mitigation. Please do not include real Telegram bot
tokens, API credentials, passwords, private keys, or personal media in the
report.

## Supported version

Security fixes are developed against the latest revision of the `main` branch.
Older revisions are not supported unless explicitly stated in a release note.

## Deployment responsibility

This project is intended for self-hosting. Operators are responsible for
keeping the host, reverse proxy, Python and JavaScript dependencies up to date;
using strong unique credentials; limiting Telegram user IDs; and protecting
backups and media files. Never expose the internal media directory directly
through the web server.

---

# 安全策略

## 报告漏洞

请勿在公开 Issue 中披露安全漏洞。

请通过仓库 Security 页面中的 **Private vulnerability reporting（私密漏洞报告）**
提交问题，并说明受影响版本、复现步骤、潜在影响和建议的缓解措施。报告中请勿包含真实的
Telegram Bot Token、API 凭据、密码、私钥或个人媒体文件。

## 支持版本

安全修复以 `main` 分支的最新版本为准；除非发布说明另有声明，旧版本不提供安全支持。

## 部署方责任

本项目用于自托管。部署者应及时更新服务器、反向代理和依赖，使用高强度独立密码，严格限制
Telegram 用户 ID，并妥善保护备份与媒体文件。请勿通过 Web 服务器直接公开内部媒体目录。
