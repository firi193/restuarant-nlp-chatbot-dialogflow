from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi import Request
import db_helper
from pydantic import BaseModel
import generic_helper
from dialogflow_fulfillment import WebhookClient
from typing import List



app = FastAPI()
item_names=[]


@app.post("/")
async def handle_request(request: Request):
    # Retrieve the JSON data from the request
    payload = await request.json()

    # Extract the necessary information from the payload
    # based on the structure of the WebhookRequest from Dialogflow
    intent = payload['queryResult']['intent']['displayName']
    parameters = payload['queryResult']['parameters']
    output_contexts = payload['queryResult']['outputContexts']

    print(payload['queryResult'])
    # # Extract the postback value from the request
    # postback = request["queryResult"]["intent"]["displayName"]

    # if postback == "call_add_all_orders":
    #     message = add_all_orders(item_names)
    #     print(message)
    
    #find postback
    # if intent=="dashes":
    #     return add_all_orders(item_names)
    
    # else:
    session_id=generic_helper.extract_session_id(output_contexts[0]['name'])

    intent_handler_dict = {
        "order.add - context:ongoing_order": add_to_order,
        "order.remove - context:ongoing_order": remove_from_order,
        "order.complete - context: ongoing-order": complete_order,
        "track.order - context: ongoing_tracking": track_order,
        "selected.item": add_to_order_from_menu,
        "show.menu": carousel_for_menu,
        "dashes": add_all_orders
    }

    return intent_handler_dict[intent](parameters, session_id)


class Card(BaseModel):
    title: str
    subtitle: str
    image_url: str
    price: str

class MenuItem(BaseModel):
    name: str
    description: str
    image_url: str
    price: str


def track_order(parameters: dict, session_id: str):
    order_id = int(parameters['number'])
    order_status = db_helper.get_order_status(order_id)
    if order_status:
        fulfillment_text = f"The order status for order id: {order_id} is: {order_status}"
    else:
        fulfillment_text = f"No order found with order id: {order_id}"

    return JSONResponse(content={
        "fulfillmentText": fulfillment_text
    })

inprogress_orders={}

#this handles new orders and orders added to an existing order
def add_to_order(parameters: dict, session_id: str):
    food_items=parameters["food-item"]
    quantities=parameters["number"]


    if len(food_items)!=len(quantities):
        fulfillment_text="sorry, can you please specify food items and quantities clearly?"
    else:
        food_dict=dict(zip(food_items,quantities))
        if session_id in inprogress_orders.keys():
             current_food_dict=inprogress_orders[session_id]
             food_dict.update(current_food_dict)
        inprogress_orders[session_id]=food_dict    

        order_str=generic_helper.get_str_from_food_dict(inprogress_orders[session_id])
        fulfillment_text=f"So far you have ordered {order_str}, do you want anything else?"
    return JSONResponse(content={
            "fulfillmentText": fulfillment_text
        })

def save_to_db(order: dict):
    next_order_id = db_helper.get_next_order_id()

    # Insert individual items along with quantity in orders table
    for food_item, quantity in order.items():
        #rcode is the return code
        rcode = db_helper.insert_order_item(
            food_item,
            quantity,
            next_order_id
        )

        #if not successful
        if rcode == -1:
            return -1

    # Now insert order tracking status
    db_helper.insert_order_tracking(next_order_id, "in progress")

    return next_order_id

# this is fired when the intent recognized is 'complete order', and it completes the order by 
# adding the orders present in that particular session(with 'save_to_db''s help of course) to the database, and outing that order from the temporary
# inprogess_orders dictionary. It also gets the total price of the order, and tells the user that the order is placed along with the total price
def complete_order(parameters: dict, session_id: str):
    if session_id not in inprogress_orders.keys():
        fulfillment_text = "I'm having trouble finding your order. Sorry! Can you place a new order please?"
    else:
        order = inprogress_orders[session_id]
        order_id = save_to_db(order)
        if order_id == -1:
            fulfillment_text = "Sorry, I couldn't process your order due to a backend error. " \
                               "Please place a new order again"
        else:
            order_total = db_helper.get_total_order_price(order_id)

            fulfillment_text = f"Awesome. We have placed your order. " \
                           f"Here is your order id # {order_id}. " \
                           f"Your order total is {order_total} which you can pay at the time of delivery!"
            
        #once the order is completed and it's put into the database, the order(identified by the specific 
        # session_id) can be removed from the in_progress_orders dictionary as it's not needed anymore, and for the process to go smoothly
        del inprogress_orders[session_id]        
    return JSONResponse(content={
            "fulfillmentText": fulfillment_text
        })


def remove_from_order(parameters: dict, session_id: str):
    if session_id not in inprogress_orders:
        return JSONResponse(content={
            "fulfillmentText": "I'm having a trouble finding your order. Sorry! Can you place a new order please?"
        })
    
    food_items = parameters["food-item"]
    current_order = inprogress_orders[session_id]

    removed_items = []
    no_such_items = []

    for item in food_items:
        if item not in current_order:
            no_such_items.append(item)
        else:
            removed_items.append(item)
            del current_order[item]

    if len(removed_items) > 0:
        fulfillment_text = f'Removed {",".join(removed_items)} from your order!'

    if len(no_such_items) > 0:
        fulfillment_text = f' Your current order does not have {",".join(no_such_items)}'

    if len(current_order.keys()) == 0:
        fulfillment_text += " You have not made any orders yet!"
    else:
        order_str = generic_helper.get_str_from_food_dict(current_order)
        fulfillment_text += f" Here is what is left in your order: {order_str}"

    return JSONResponse(content={
        "fulfillmentText": fulfillment_text
    })



def carousel_for_menu(parameters: dict, session_id: str):
    menu_items = [
        MenuItem(name="Pizza", description="Delicious pizza with tomato sauce and cheese", image_url="https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQARsVwuWsRP9uOqVZN3u2zQ5ZzX3WgGI9Me_o2_Nt95KG-r-V73ySoiaWwe72IrW4WrVc&usqp=CAU", price="$12.99"),
        MenuItem(name="Pasta", description="Pasta with creamy alfredo sauce", image_url="https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTsxn1hfH6IXqszmSGwGQhAqPk-GxJ8z-PALA&usqp=CAU", price="$15.59"),
        MenuItem(name="Salad", description="Fresh salad with lettuce, tomatoes, and cucumbers", image_url="https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRK4jKOU80jHcJwudHOTBvbPhldyhq617Wtn9Dv0MfnB9DrIunqQQC39uYyadP38rFdpqo&usqp=CAU", price="$5.99")
    ]


    # Create the response with the list of cards
    response = {
        "fulfillmentMessages": [
            {
                "card": {
                    "title": f"{item.name} - {item.price}",
                    "subtitle": item.description,
                    "imageUri": item.image_url,
                    "buttons": [
                        {
                            "text": "Select",
                            "postback": f"Selected {item.name}"#the postbacks trigger a select.menu intent
                        }
                    ]
                },
            } for item in menu_items
        ]
    }

    # Add suggestion chips for each menu item
    suggestions = [{"title": item.name} for item in menu_items]
    response["fulfillmentMessages"].append({
        "platform": "ACTIONS_ON_GOOGLE",
        "suggestions": {
            "suggestions": suggestions
        }
    })

    # Add a card with a button to complete the order
    response["fulfillmentMessages"].append({
        "card": {
            "title": "Complete your order",
            "subtitle": "",
            "imageUri": "",
            "buttons": [
                {
                    "text": "Finish",
                    "postback": "-----"
                }
            ]
        }
    })

    print(item_names)
    return response


#
def add_to_order_from_menu(parameters: dict, session_id: str):
    # Get the postback value
    global item_names
    item_name = parameters['food-item']
    
    # Store the item.name value in a list
    item_names.append(item_name)
    print(f"I want {', '.join(item_names)}")
    return item_names
    # return JSONResponse(content={
    #     "fulfillmentText": item_name
    # })



def add_all_orders(parameters: dict, session_id: str,item_names=item_names):
    message=f"You have added {', '.join(item_names)} to your order"
    return JSONResponse(content=
                        {
                            "fulfillmentText": message
                            
    })

# def handle_button_click(parameters: dict, session_id: str):
#     # Get the selected item and quantity from the parameters
#     selected_item = parameters["selected_item"]
#     quantity = int(parameters["quantity"])

#     # Retrieve the current order from the session variable
#     order = session.get(session_id, [])

#     # Add the selected item and quantity to the order
#     order.append((selected_item, quantity))

#     # Update the session variable with the new order
#     session[session_id] = order

#     # Return an empty response
#     return {}
