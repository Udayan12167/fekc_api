#!flask/bin/python
from flask import Flask, request, jsonify
from flask_restful import Resource, Api, reqparse
from pymongo import MongoClient
from bson.objectid import ObjectId
from bson.json_util import dumps
from pushjack import GCMClient
from ast import literal_eval
import json
import os
from datetime import datetime

app = Flask(__name__)
api = Api(app)

gcm_client = GCMClient(api_key='AIzaSyC2KtWM8Ce1lWrtIN-Ql2J0c5bPZc0iLQc')


def connect():
    connection = MongoClient("mongodb://udayan12167:Syncmaster2033@ds023098.mlab.com:23098/fekc")
    handle = connection["fekc"]
    return handle

handle = connect()

errors = {
    'AuthenticationError': {
        'message': "Token was incorrect",
        'status': 200,
    },
    'ResourceDoesNotExist': {
        'message': "A resource with that ID no longer exists.",
        'status': 410,
        'extra': "Any extra information you want.",
    },
}

user_parser = reqparse.RequestParser()
user_parser.add_argument('fbtoken')
user_parser.add_argument('fbid')
user_parser.add_argument('gcmtoken')


class User(Resource):
    def get(self, user_id):
        user = handle.users.find_one({'_id': ObjectId(user_id)})
        return dumps(user)

    def delete(self, user_id):
        deleted = handle.users.delete_one({'_id': ObjectId(user_id)})
        return {"delete_count": deleted.deleted_count}, 204

    def put(self, user_id):
        args = user_parser.parse_args()
        user = handle.users.find_one({'_id': ObjectId(user_id)})
        if user["fbtoken"] == args["fbtoken"]:
            updated = handle.users.update_one({'_id': ObjectId(user_id)},
                                              {'$set': args})
            return {"mod_count": updated.modified_count}, 201
        return errors["AuthenticationError"]


class UserList(Resource):
    def post(self):
        args = user_parser.parse_args()
        check = handle.users.find_one({'fbid': args["fbid"]})
        if check:
            handle.users.update_one({'fbid': args["fbid"]},
                                    {'$set': args})
            return {'oid': str(check["_id"]), 'userStatusCode': 0}
        user = {'fbtoken': args["fbtoken"],
                'fbid': args["fbid"]}
        user_id = handle.users.insert_one(user)
        return {'oid': str(user["_id"]), 'userStatusCode': 1}


task_track_parser = reqparse.RequestParser()
task_track_parser.add_argument('fbtoken')


class TrackedTaskList(Resource):
    def get(self, user_id):
        args = task_track_parser.parse_args()
        user = handle.users.find_one({'_id': ObjectId(user_id)})
        if user["fbtoken"] == args["fbtoken"]:
            task_mappings = handle.tracked_tasks.find({'user_id': user["fbid"]})
            tasks = []
            for t in task_mappings:
                task_id = t["tracked_task"]
                task = handle.tasks.find_one({'_id': ObjectId(task_id)})
                if task:
                    task_dict = literal_eval(task["task"])
                    task_dict["messageSet"] = t["message_set"]
                    if t["message_set"]:
                        task_dict["message"] = t["message"]
                    task_dict["trackingFriendId"] = t["tracking_friend"]
                    task_dict["trackedTaskId"] = t["tracked_task"]
                    tasks.append(task_dict)
            ret_json_dict = {"tasks": []}
            ind = 0
            for task in tasks:
                ret_json_dict["tasks"].append(task)
                ind += 1
            print ret_json_dict
            return jsonify(**ret_json_dict)
        return errors["AuthenticationError"]


message_parser = reqparse.RequestParser()
message_parser.add_argument('message')
message_parser.add_argument('user_id')
message_parser.add_argument('fbtoken')


class TrackedTaskMessage(Resource):
    def put(self, tracked_task_id):
        args = message_parser.parse_args()
        user = handle.users.find_one({'_id': ObjectId(args["user_id"])})
        if user["fbtoken"] == args["fbtoken"]:
            tracked_task = handle.tracked_tasks.update_one({
                'user_id': user["fbid"],
                'tracked_task': tracked_task_id},
                {"$set": {"message": args["message"], "message_set": 1}})
            print tracked_task
            return {"message": "success"}
        return errors["AuthenticationError"]

all_message_parser = reqparse.RequestParser()
all_message_parser.add_argument('task_id')
all_message_parser.add_argument('fbtoken')


class Messages(Resource):
    def get(self, user_id):
        args = all_message_parser.parse_args()
        user = handle.users.find_one({'_id': ObjectId(user_id)})
        if user["fbtoken"] == args["fbtoken"]:
            print "entered"
            messages = handle.tracked_tasks.find({
                'tracking_friend': user["fbid"],
                'tracked_task': args["task_id"]})
            a = list(messages)
            print a
            message_dict = {"messages": []}
            ind = 0
            for message in a:
                if str(message["message_set"]) == "1":
                    user_message_map = {'friendId': message["user_id"],
                                        'message': message["message"]}
                    message_dict["messages"].append(user_message_map)
                else:
                    user_message_map = {'friendId': message["user_id"],
                                        'message': "No message"}
                    message_dict["messages"].append(user_message_map)
                ind += 1
            return jsonify(**message_dict)

task_parser = reqparse.RequestParser()
task_parser.add_argument('task')
task_parser.add_argument('user_id')


class Tasks(Resource):
    def post(self):
        args = task_parser.parse_args()
        print args["task"]
        task = {'user_id': args["user_id"],
                'task': args["task"]}
        tracked_friends = literal_eval(args["task"])["friends"]
        tracking_friend = handle.users.find_one(
            {'_id': ObjectId(args["user_id"])})
        task_id = handle.tasks.insert_one(task)
        for friend in tracked_friends:
            task_entry = {'user_id': friend,
                          'tracked_task': str(task["_id"]),
                          'message_set': 0,
                          'tracking_friend': tracking_friend["fbid"]}
            print task_entry
            handle.tracked_tasks.insert_one(task_entry)
            f = handle.users.find_one({'fbid': friend})
            if f:
                notification_dict = literal_eval(args["task"])
                notification_dict["friendfbid"] = tracking_friend["fbid"]
                gcm_client.send(f["gcmtoken"] ,"Task created" ,notification=notification_dict)
        return {'tid': str(task["_id"])}


class Task(Resource):
    def delete(self, task_id):
        violation_result = handle.violations.delete_many({'task_id': task_id})
        win_result = handle.winwin.delete_many({'task_id': task_id})
        tracked_result = handle.tracked_tasks.delete_many(
            {'tracked_task': task_id})
        task = handle.tasks.delete_many({'_id': ObjectId(task_id)})
        return {"deleted": task.deleted_count}


violation_parser = reqparse.RequestParser()
violation_parser.add_argument('task_id')
violation_parser.add_argument('user_id')
violation_parser.add_argument('fbtoken')
violation_parser.add_argument('timestamp')


class Violation(Resource):
    def post(self):
        args = violation_parser.parse_args()
        violation = {'user_id': args['user_id'],
                     'task_id': args['task_id'],
                     'timestamp': datetime.now()}
        user = handle.users.find_one({'_id': ObjectId(args["user_id"])})
        if user["fbtoken"] == args["fbtoken"]:
            handle.violations.insert_one(violation)
            task = handle.tasks.find_one({'_id': ObjectId(args["task_id"])})
            friend_list = literal_eval(task["task"])["friends"]
            for friend in friends:
                f = handle.users.find_one({'fbid': friend})
                if f:
                    notification_dict = literal_eval(task["task"])
                    notification_dict["friendfbid"] = user["fbid"]
                    gcm_client.send(f["gcmtoken"],
                                    "Task violated",
                                    notification=notification_dict)
            return {'logged': "success"}

violation_list_parser = reqparse.RequestParser()
violation_list_parser.add_argument('fbtoken')


class TaskViolationList(Resource):
    def get(self, task_id):
        args = violation_list_parser.parse_args()
        user = handle.users.find_one({'_id': ObjectId(args["user_id"])})
        if user["fbtoken"] == args["fbtoken"]:
            violations = handle.violations.find({'task_id': task_id})
            v = list(violations)
            violations_dict = {"violations": []}
            for violation in v:
                violations_dict["violations"].append(violation)
            return jsonify(**violations_dict)


winwin_parser = reqparse.RequestParser()
winwin_parser.add_argument('task_id')
winwin_parser.add_argument('user_id')
winwin_parser.add_argument('fbtoken')
winwin_parser.add_argument('timestamp')


class WinWin(Resource):
    def post(self):
        args = winwin_parser.parse_args()
        winwin = {'user_id': args['user_id'],
                  'task_id': args['task_id'],
                  'timestamp': datetime.now()}
        user = handle.users.find_one({'_id': ObjectId(args["user_id"])})
        if user["fbtoken"] == args["fbtoken"]:
            handle.winwin.insert_one(winwin)
            return {'logged': "success"}

winwin_list_parser = reqparse.RequestParser()
winwin_list_parser.add_argument('fbtoken')


class TaskWinWinList(Resource):
    def get(self, task_id):
        args = winwin_list_parser.parse_args()
        user = handle.users.find_one({'_id': ObjectId(args["user_id"])})
        if user["fbtoken"] == args["fbtoken"]:
            wins = handle.winwin.find({'task_id': task_id})
            w = list(wins)
            wins_dict = {"wins": []}
            for win in w:
                wins_dict["wins"].append(win)
            return jsonify(**wins_dict)


api.add_resource(UserList, '/users')
api.add_resource(User, '/user/<user_id>')
api.add_resource(Tasks, '/tasks')
api.add_resource(TrackedTaskList, "/tracked_tasks/<user_id>")
api.add_resource(TrackedTaskMessage, "/message/<tracked_task_id>")
api.add_resource(Messages, "/messages/<user_id>")
api.add_resource(Violation, "/violation")
api.add_resource(TaskViolationList, "/violations/<task_id>")
api.add_resource(WinWin, "/win")
api.add_resource(TaskWinWinList, "/wins/<task_id>")
api.add_resource(Task, '/task/<task_id>')

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host='0.0.0.0')
