import os
import re
from string import letters

import webapp2
import jinja2
import hashlib
import random
import string
import json
import logging
from time import time
from google.appengine.ext import db
from google.appengine.api import memcache

template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader = jinja2.FileSystemLoader(template_dir),
                               autoescape = True)

def render_str(template, **params):
    t = jinja_env.get_template(template)
    return t.render(params)

class BlogHandler(webapp2.RequestHandler):
    def write(self, *a, **kw):
        self.response.out.write(*a, **kw)

    def render_str(self, template, **params):
        return render_str(template, **params)

    def render(self, template, **kw):
        self.write(self.render_str(template, **kw))

def render_post(response, post):
    response.out.write('<b>' + post.subject + '</b><br>')
    response.out.write(post.content)

class MainPage(BlogHandler):
  def get(self):
      self.write('Hello, Udacity!')

##### blog stuff

def blog_key(name = 'default'):
    return db.Key.from_path('blogs', name)

class Post(db.Model):
    subject = db.StringProperty(required = True)
    content = db.TextProperty(required = True)
    created = db.DateTimeProperty(auto_now_add = True)
    last_modified = db.DateTimeProperty(auto_now = True)

    def render(self):
        self._render_text = self.content.replace('\n', '<br>')
        return render_str("post.html", p = self)
cacheage=None
def getPosts(update=False):
    global cacheage
    key="top"
    posts=memcache.get(key)
    if posts is None or update:
        logging.error("DB QUERY")
        posts = db.GqlQuery("select * from Post order by created desc limit 10")
        cacheage=time()
    posts=list(posts)
    memcache.set(key,posts)
    return posts

class BlogFront(BlogHandler):
    def get(self):
        global cacheage
        posts=getPosts()
        if cacheage:
            age=round(time()-cacheage,2)
        else:
            age=None
        self.render('front.html', posts = posts,time=age)

postAge=None
def getNewPost(post_id):
    global postAge
    access="%s"%post_id
    post=memcache.get(access)
    if post is None:
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        logging.error("New post lookup occured")
        post = db.get(key)
        postAge=time()
    memcache.set(access,post)
    return post

class PostPage(BlogHandler):
    def get(self, post_id):
        global postAge
        post=getNewPost(post_id)
        if postAge:
            age=round(time()-postAge,2)
        else:
            age=None
        if not post:
            self.error(404)
            return

        self.render("permalink.html", post = post,time=age)

class NewPost(BlogHandler):
    def get(self):
        self.render("newpost.html")

    def post(self):
        subject = self.request.get('subject')
        content = self.request.get('content')

        if subject and content:
            p = Post(parent = blog_key(), subject = subject, content = content)
            p.put()
            memcache.flush_all()
            self.redirect('/blog/%s' % str(p.key().id()))
        else:
            error = "subject and content, please!"
            self.render("newpost.html", subject=subject, content=content, error=error)



###### Unit 2 HW's
class Rot13(BlogHandler):
    def get(self):
        self.render('rot13-form.html')

    def post(self):
        rot13 = ''
        text = self.request.get('text')
        if text:
            rot13 = text.encode('rot13')

        self.render('rot13-form.html', text = rot13)


USER_RE = re.compile(r"^[a-zA-Z0-9_-]{3,20}$")
def valid_username(username):
    return username and USER_RE.match(username)

PASS_RE = re.compile(r"^.{3,20}$")
def valid_password(password):
    return password and PASS_RE.match(password)

EMAIL_RE  = re.compile(r'^[\S]+@[\S]+\.[\S]+$')
def valid_email(email):
    return not email or EMAIL_RE.match(email)

def salter(username,password,salt=None):
    if not salt:
        salt=''.join([random.choice(string.ascii_letters) for n in xrange(5)])
    hashpw=hashlib.sha256(username+password+salt).hexdigest()+"|"+salt
    return hashpw


class Signup(BlogHandler):

    def get(self):
        self.render("signup-form.html")

    def post(self):
        have_error = False
        username = str(self.request.get('username'))
        password = self.request.get('password')
        verify = self.request.get('verify')
        email = self.request.get('email')

        params = dict(username = username,
                      email = email)

        if not valid_username(username):
            params['error_username'] = "That's not a valid username."
            have_error = True

        if not valid_password(password):
            params['error_password'] = "That wasn't a valid password."
            have_error = True
        elif password != verify:
            params['error_verify'] = "Your passwords didn't match."
            have_error = True

        if not valid_email(email):
            params['error_email'] = "That's not a valid email."
            have_error = True

        if have_error:
            self.render('signup-form.html', **params)
        else:
            cursor=db.GqlQuery("SELECT * from User WHERE username='%s'"%username)
            dupeCheck=cursor.get()
            if not dupeCheck:
                saltedpw=salter(username,password)
                person=User(username=username,password=saltedpw,email=email)
                person.put()
                self.response.headers.add_header('Set-Cookie', 'userid=%s; Path=/'%person.key().id())
                self.redirect('/welcome')
            else:
                params['error_username'] = "That username already exists"
                self.render('signup-form.html', **params)

class User(db.Model):
    username=db.StringProperty(required=True)
    password=db.StringProperty(required=True)
    email=db.StringProperty()
    userNum=db.IntegerProperty()

class Welcome(BlogHandler):
    def get(self):
        userid = self.request.cookies.get('userid')
        if str(userid).isdigit():
            person=User.get_by_id(int(userid))
            if person:
                username=person.username
                self.render('welcome.html', username = username)
            else:
                self.redirect('/signup')
        else:
            self.redirect('/signup')


class Login(BlogHandler):
    def get(self):
        self.render('login.html')
    def post(self):
        username=str(self.request.get("username"))
        password=self.request.get("password")
        curs=db.GqlQuery("SELECT * from User WHERE username='%s'"%username)
        person=curs.get()
        if person:
            saltedPass=person.password
            userSalt=str(saltedPass).split('|')[1]
            userPass=salter(username,password,userSalt)
            if userPass==saltedPass:
                self.response.headers.add_header('Set-Cookie', 'userid=%s; Path=/'%person.key().id())
                self.redirect('/welcome')
            else:
                self.render('login.html',username=username,error_password="Wrong Password")
        else:
            self.render('login.html',username=username,error_username="User doesnt exist")

class Logout(BlogHandler):
    def get(self):
        self.response.headers.add_header('Set-Cookie', 'userid=""; Path=/')
        self.render('login.html')

class BlogJson(BlogHandler):
    def get(self):
        self.response.headers['Content-Type'] = 'application/json'
        posts = db.GqlQuery("select * from Post order by created desc limit 10")
        blogJson=[]
        for p in posts:
            blogPost={'subject':p.subject,
                       'content':p.content,
                       'created':str(p.created)}
            blogJson.append(blogPost)
        self.response.write(json.dumps(blogJson))

class PostPageJson(BlogHandler):
    def get(self,post_id):
        self.response.headers['Content-Type'] = 'application/json'
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)

        if not post:
            self.error(404)
            return

        blogPost={'Subject':post.subject,
                  'Content':post.content,
                  'Created':str(post.created)}
        self.response.write(json.dumps(blogPost))

app = webapp2.WSGIApplication([('/', MainPage),
                               ('/rot13', Rot13),
                               ('/signup', Signup),
                               ('/welcome', Welcome),
                               ('/blog/?', BlogFront),
                               ('/blog/([0-9]+)', PostPage),
                               ('/blog/newpost', NewPost),
                               ('/login',Login),
                               ('/logout',Logout),
                               ('/blog.json',BlogJson),
                               ('/blog/([0-9]+).json',PostPageJson)
                               ],
                              debug=True)
