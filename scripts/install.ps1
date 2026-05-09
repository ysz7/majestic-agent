Write-Host "Installing Majestic..."

# Check Python
$version = python --version 2>&1
if ($version -notmatch "3\.(1[1-9]|[2-9][0-9])") {
    Write-Error "Python 3.11+ required"
    exit 1
}

pip install -e . --quiet
Write-Host "✓ Majestic installed. Run 'majestic setup' to get started."
