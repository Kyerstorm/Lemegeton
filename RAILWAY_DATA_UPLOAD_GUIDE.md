# 📤 Upload Local Data to Railway Volume

This guide helps you transfer your local `data/` files to your Railway deployment.

## 📦 What's Been Prepared

✅ **Created:** `data_upload.zip` (0.13 MB)
- Contains 23 files including:
  - `database.db` - Main database
  - `dashboard_guilds.db` - Dashboard configs
  - All JSON files (profile cache, news, etc.)
  - Other database files

✅ **Created:** `extract_data_railway.py`
- Extraction script to run on Railway

---

## 🚀 Upload Methods

### **Method 1: Deploy & Extract (Recommended)**

This method deploys the extraction script and zip file to Railway.

#### Step 1: Add Files to Git

```powershell
git add data_upload.zip extract_data_railway.py
git commit -m "Add data upload files for Railway deployment"
git push origin multi_guild
```

#### Step 2: Deploy to Railway

```powershell
railway up
```

#### Step 3: Extract Data on Railway

```powershell
# Run the extraction script
railway run python extract_data_railway.py

# Restart the bot to use the new data
railway restart
```

#### Step 4: Verify

```powershell
# Check logs to see if bot is using the data
railway logs --follow

# Or check the data directory
railway run ls -la /app/data
```

---

### **Method 2: Manual Upload via Railway Shell**

If you prefer to upload files one at a time:

#### Step 1: Open Railway Shell

```powershell
railway shell
```

#### Step 2: Upload Files (from another terminal)

While railway shell is open in one terminal, open another terminal and run:

```powershell
# Upload the zip file
railway run --service=your-service -- bash -c "cat > /app/data_upload.zip" < data_upload.zip

# Extract it
railway run python extract_data_railway.py
```

---

### **Method 3: Environment Variable Upload (For Small Files)**

For individual small JSON files (< 100KB):

```powershell
# Example: Upload a specific JSON file
$content = Get-Content "data_upload\news_accounts.json" -Raw
railway run python -c "import os; f=open('/app/data/news_accounts.json','w'); f.write('''$content'''); f.close()"
```

---

## 🔍 Verify Upload Success

After uploading, verify your files are in the Railway volume:

```powershell
# List all files in /app/data
railway run ls -lah /app/data

# Check specific database
railway run ls -lh /app/data/database.db

# Check database size
railway run du -sh /app/data/*
```

---

## 📊 Expected Results

After successful upload, your `/app/data` should contain:

```
/app/data/
├── database.db (main database)
├── dashboard_guilds.db (dashboard configs)
├── profile_cache.json (user profiles - 12hr cache)
├── news_accounts.json (news monitoring)
├── news_filters.json (news filters)
├── news_metadata.json (news metadata)
├── welcome_dm.json (welcome messages)
├── 3x3_gallery.json (user 3x3 grids)
├── account_whitelists.json (whitelists)
├── affinity_cache.json (affinity calculations)
├── leaderboard_cache.json (leaderboards)
└── ... (other files)
```

---

## 🐛 Troubleshooting

### Issue: "zip file not found"

**Solution:** Make sure to deploy the zip file first:
```powershell
git add data_upload.zip
git commit -m "Add data upload"
git push
railway up
```

### Issue: "Permission denied"

**Solution:** Check that the volume is mounted correctly:
1. Go to Railway dashboard
2. Settings → Volumes
3. Verify `/app/data` is mounted

### Issue: "Files not persisting after restart"

**Solution:** Ensure you have a Railway volume:
1. Railway dashboard → Your service
2. Settings → Add Volume
3. Mount path: `/app/data`

---

## 🎯 Quick Start (All-in-One)

```powershell
# 1. Add and deploy files
git add data_upload.zip extract_data_railway.py RAILWAY_DATA_UPLOAD_GUIDE.md
git commit -m "Add data upload for Railway"
git push origin multi_guild
railway up

# 2. Extract data
railway run python extract_data_railway.py

# 3. Restart bot
railway restart

# 4. Verify
railway logs --follow
```

---

## 📝 Notes

- **Backup First:** Your local files remain unchanged
- **Volume Required:** Ensure Railway volume is mounted to `/app/data`
- **One-Time Upload:** You only need to do this once
- **Future Updates:** Bot will update data files automatically

---

## ✅ Post-Upload Checklist

- [ ] Files extracted to `/app/data`
- [ ] Bot restarted with `railway restart`
- [ ] Logs show successful database connections
- [ ] Test commands in Discord (`/help`, `/profile`, etc.)
- [ ] Verify user data is present

---

**Need Help?** Check Railway logs: `railway logs --follow`

