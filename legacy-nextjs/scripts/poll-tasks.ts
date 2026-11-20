import { pollOneTask } from "../lib/tasks";
pollOneTask().then((task) => { if (task) console.log(`Polled ${task.id}: ${task.status}`); }).catch((error) => { console.error(error); process.exitCode = 1; });
