const mysql = require("mysql2");


const connection = mysql.createConnection({

    host: "localhost",

    user: "root",

    password: "Brun#@bh1",

    database: "evcharger"

});


connection.connect((error)=>{

    if(error){

        console.log("MySQL Connection Failed");

        console.log(error);

    }

    else{

        console.log("MySQL Connected Successfully");

    }

});


module.exports = connection;