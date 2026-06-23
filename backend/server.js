const express = require("express");
const cors = require("cors");


const app = express();


// Allow frontend connection
app.use(cors());


// Read JSON data from frontend
app.use(express.json());



// Database connection
const db = require("./database");



// Routes

const usersRoute = require("./routes/users");
const chargerRoute = require("./routes/charger");
const sessionsRoute = require("./routes/sessions");
const qrRoute = require("./routes/qr");



// API connections

app.use("/api/auth", usersRoute);

app.use("/api/station", chargerRoute);

app.use("/api/session", sessionsRoute);

app.use("/api/qr", qrRoute);





// Test API

app.get("/",(req,res)=>{


    res.send("EV Charger Backend Running");


});






// Start server

app.listen(3000,()=>{


    console.log("Server started on port 3000");


});