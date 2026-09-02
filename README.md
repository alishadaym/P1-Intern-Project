# P1-Intern-Project
- Track guest location in mall

## Simulate restroom occupancy

The simulator starts automatically when the Flask app starts:

```powershell
python app.py
```

It randomly occupies available restroom cubicles and returns each occupied
cubicle to `Available` after a random duration between two and five minutes.
Occupancy happens in realistic waves based on the time of day, with a
five-minute empty gap between waves. The navigation page refreshes the counts
automatically every five seconds.
