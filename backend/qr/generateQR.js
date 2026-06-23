const QRCode = require("qrcode");

const db = require("../database");



const websiteURL = "http://localhost:5500/?charger_id=";



const query = "SELECT charger_id FROM chargers";



db.query(query,(error,result)=>{


    if(error){

        console.log("Database Error");

        console.log(error);

    }


    else{


        result.forEach((charger)=>{


            const chargerID = charger.charger_id;


            const url = websiteURL + chargerID;



            QRCode.toFile(

                `${chargerID}.png`,

                url,

                function(err){


                    if(err){

                        console.log(err);

                    }

                    else{

                        console.log(
                        "QR Created:",
                        chargerID
                        );

                    }


                }


            );



        });



    }


});