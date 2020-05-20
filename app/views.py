"""
Flask Documentation:     http://flask.pocoo.org/docs/
Jinja2 Documentation:    http://jinja.pocoo.org/2/documentation/
Werkzeug Documentation:  http://werkzeug.pocoo.org/documentation/
This file creates your application.
"""

import os
import datetime
from app import app, db, login_manager, csrf
from flask import render_template, request, redirect, url_for, flash, jsonify, g
from flask_login import login_user, logout_user, current_user, login_required
from app.forms import LoginForm, RegisterForm,  PostsForm
from app.models import Users, Likes, Follows, Posts
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash

#Using JWT
import jwt
from functools import wraps
import base64



# Create a JWT @requires_auth decorator
# This decorator can be used to denote that a specific route should check
# for a valid JWT token before displaying the contents of that route.
def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get('Authorization', None)
        if not auth:
            return jsonify({'code': 'authorization_header_missing', 'description': 'Authorization header is expected'}), 401

        parts = auth.split()

        if parts[0].lower() != 'bearer':
            return jsonify({'code': 'invalid_header', 'description': 'Authorization header must start with Bearer'}), 401
        elif len(parts) == 1:
            return jsonify({'code': 'invalid_header', 'description': 'Token not found'}), 401
        elif len(parts) > 2:
            return jsonify({'code': 'invalid_header', 'description': 'Authorization header must be Bearer + \s + token'}), 401

        token = parts[1]

        try:
            payload = jwt.decode(token, app.config['SECRET_KEY'])

        except jwt.ExpiredSignature:
            return jsonify({'code': 'token_expired', 'description': 'token is expired'}), 401
        except jwt.DecodeError:
            return jsonify({'code': 'token_invalid_signature', 'description': 'Token signature is invalid'}), 401

        g.current_user = user = payload
        return f(*args, **kwargs)

    return decorated


# Routing for your application.

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def index(path):
    """
    Because we use HTML5 history mode in vue-router we need to configure our
    web server to redirect all routes to index.html. Hence the additional route
    "/<path:path".

    Also we will render the initial webpage and then let VueJS take control.
    """
    #return app.send_static_file('index.html')
    return render_template('index.html')



#api route to allow a user to register for the application
@app.route("/api/users/register", methods=["POST"])
def register():
    form = RegisterForm(request.form)
    photo = request.files["photo"]
    form.photo.data = photo
    if request.method == "POST" and form.validate_on_submit() == True:
        username = form.username.data
        password = form.password.data
        firstname = form.firstname.data
        lastname = form.lastname.data
        email = form.email.data
        location = form.location.data
        bio = form.biography.data
        photo = form.photo.data
        photo = assignPath(form.photo.data)

        try:
            #create user object and add to database
            user = Users(username, password, firstname, lastname, email, location, bio, photo)
            if user is not None:
                db.session.add(user)
                db.session.commit()

                #flash message to indicate the a successful entry
                success = "User sucessfully registered"
                return jsonify(message=success), 201

        except Exception as e:
            print(e)
            db.session.rollback()
            error = "An error occured with the server. Try again!"
            return jsonify(error=error), 401

    #flash message to indicate registration failure
    failure = "Error: Invalid/Missing user information"
    return jsonify(error=failure), 401


#api route to allow the user to login into their profile on the application
@app.route("/api/auth/login", methods=["POST"])
def login():
    form = LoginForm(request.form)
    print(form.data)
    if request.method == "POST" and form.validate_on_submit() == True:
        username = form.username.data
        password = form.password.data

        #Query the database to retrive the recording corresponding to the given username and password
        user = db.session.query(Users).filter_by(username=username).first()

        if user is not None and check_password_hash(user.password, password):

            login_user(user)

            #creates bearer token for user
            payload = {'user': user.username}
            jwt_token = jwt.encode(payload, app.config['SECRET_KEY'], algorithm = 'HS256').decode('utf-8')

            #Flash message to indicate a successful login
            success = "User successfully logged in."
            return jsonify(message=success, token=jwt_token, user_id=user.id)

        error = "Incorrect username or password"
        return jsonify(error=error), 401

    #Flash message to indicate a failed login
    failure = "Failed to login user"
    return jsonify(error=failure)


#api route to allow the user to logout
@app.route("/api/auth/logout", methods=["GET"])
@requires_auth
def logout():
    logout_user()

    #Flash message indicating a successful logout
    success = "User successfully logged out."
    return jsonify(message=success)


#api route to get a users details
@app.route("/api/users/<user_id>", methods=["GET"])
@requires_auth
def userDetails(user_id):
    try:
        user = db.session.query(Users).filter_by(id=user_id).first()
        isFollowing = current_user.id in [ follower.follower_id for follower in user.followers] #checks if the current user if following this user

        current = {"id": user.id, "username": user.username, "firstname": user.first_name, "lastname": user.last_name, "email": user.email, "location": user.location, "biography": user.biography,
        "profile_photo": os.path.join(app.config['GET_FILE'], user.profile_photo), "joined": user.joined_on.strftime("%b %Y"), "isFollowing": isFollowing, "posts": []}

        return jsonify(user=current)
    except Exception as e:
        print(e)

        error = "Internal server error"
        return jsonify(error=error), 401


#api route to display all users and their posts
@app.route("/api/posts", methods=["GET"])
@requires_auth
def allPosts():
    try:
        posts = []
        userPosts = db.session.query(Posts).order_by(Posts.created_on.desc()).all()

        for post in userPosts:#                                      this is using the "Users" backref that we assigned to the posts table

            likes = [like.user_id for like in post.likes]
            isLiked = current_user.id in likes
            username = db.session.query(Users).filter_by(id=post.user_id).first().username
            profile_picture = db.session.query(Users).filter_by(id=post.user_id).first().profile_photo
            p = {"id": post.id, "user": username,"user_id": post.user_id, "profile_picture": os.path.join(app.config['GET_FILE'], profile_picture), "photo": os.path.join(app.config['GET_FILE'], post.photo), "caption": post.caption, "created_on": post.created_on.strftime("%d %b %Y"), "likes": len(post.likes), "isLiked": isLiked}
            posts.append(p)
        return jsonify(posts=posts), 201
    except Exception as e:
        print(e)

        error = "Internal server error"
        return jsonify(error=error), 401


#api route to create and display the posts for a specific user
@app.route("/api/users/<user_id>/posts", methods=["POST", "GET"])
@requires_auth
def userPosts(user_id):
    form = PostsForm()
    if request.method == "POST" and form.validate_on_submit() == True:
        try:
            caption = form.caption.data
            photo = assignPath(form.photo.data)
            post = Posts(photo, caption, user_id)
            db.session.add(post)
            db.session.commit()

            #Flash message to indicate a post was added successfully
            success = "Successfully created a new post"
            return jsonify(message=success), 201
        except Exception as e:
            print(e)

            error = "Internal server error"
            return jsonify(error=error), 401

    else:
        try:
            #Gets the current user to add/display posts to
            userPosts = db.session.query(Posts).filter_by(user_id=user_id).all()


            posts = []
            for post in userPosts:
                p = {"id": post.id, "user_id": post.user_id,"photo": os.path.join(app.config['GET_FILE'], post.photo), "description": post.caption, "created_on": post.created_on.strftime("%d %b %Y")}
                posts.append(p)

            return jsonify(posts=posts)
        except Exception as e:
            print(e)

            error = "Internal server error"
            return jsonify(error=error), 401

    #Flash message to indicate an error occurred
    failure = "Failed to create/display posts"
    return jsonify(error=failure), 401



#api route for a user to follow another user
@app.route("/api/users/<user_id>/follow", methods=["POST", "GET"])
@requires_auth
def following(user_id):
    print("here")
    if request.method == "POST":
        try:
            id = current_user.id
            follow = Follows(id, user_id)
            db.session.add(follow)
            db.session.commit()

            #Flash message to indicate a successful following
            success = "You are now following that user"
            return jsonify(message=success), 201
        except Exception as e:
            print(e)

            #Flash message to indicate that an error occurred
            failure = "Internal error. Failed to follow user"
            return jsonify(error=failure), 401
    else:
        try:
            followers = db.session.query(Follows).filter_by(user_id=user_id).all()
            return jsonify(followers=len(followers)), 201
        except Exception as e:
            print(e)

            error = "Internal server error!"
            return jsonify(error=error), 401



#api route to set a like on a current post
@app.route("/api/posts/<post_id>/like", methods=["POST"])
@requires_auth
def likePost(post_id):
    post = db.session.query(Posts).filter_by(id=post_id).first()
    if current_user.is_authenticated():
        id = current_user.id
        like = Likes(id, post_id)
        db.session.add(like)
        db.session.commit()
        return jsonify(message="Post Liked!", likes=len(post.likes)), 201

    #Flash message to indicate that an error occurred
    failure = "Failed to like post"
    return jsonify(error=failure)


#Saves the uploaded photo to a folder
def assignPath(upload):
    filename = secure_filename(upload.filename)
    upload.save(os.path.join(
                app.config['UPLOAD_FOLDER'], filename
    ))
    return filename

@login_manager.user_loader
def load_user(user_id):
    return Users.query.get(user_id)

@login_manager.unauthorized_handler
def unauthorized_handler():
    return render_template("/")


###
# The functions below should be applicable to all Flask apps.
###

@app.route('/<file_name>.txt')
def send_text_file(file_name):
    """Send your static text file."""
    file_dot_text = file_name + '.txt'
    return app.send_static_file(file_dot_text)


@app.after_request
def add_header(response):
    """
    Add headers to both force latest IE rendering engine or Chrome Frame,
    and also to cache the rendered page for 10 minutes.
    """
    response.headers['X-UA-Compatible'] = 'IE=Edge,chrome=1'
    response.headers['Cache-Control'] = 'public, max-age=0'
    return response


@app.errorhandler(404)
def page_not_found(error):
    """Custom 404 page."""
    return render_template('404.html'), 404


if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port="8080")
