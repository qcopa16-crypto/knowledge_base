import { createRouter, createWebHistory } from 'vue-router'
import { isAuthenticated } from '../store/auth'
import Layout from '../layouts/Layout.vue'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/Login.vue'),
    meta: { title: '登录', guestOnly: true },
  },
  {
    path: '/register',
    name: 'register',
    component: () => import('../views/Register.vue'),
    meta: { title: '注册', guestOnly: true },
  },
  {
    path: '/',
    component: Layout,
    children: [
      {
        path: '',
        name: 'home',
        component: () => import('../views/Home.vue'),
        meta: { title: '文档管理', requiresAuth: true },
      },
      {
        path: 'categories',
        name: 'categories',
        component: () => import('../views/CategoryManage.vue'),
        meta: { title: '分类管理', requiresAuth: true },
      },
      {
        path: 'users',
        name: 'users',
        component: () => import('../views/UserManage.vue'),
        meta: { title: '用户管理', requiresAuth: true },
      },
      {
        path: 'chat',
        name: 'chat',
        component: () => import('../views/Chat.vue'),
        meta: { title: '智能问答', requiresAuth: true },
      },
      {
        path: 'upload',
        name: 'upload',
        component: () => import('../views/Upload.vue'),
        meta: { title: '文档上传', requiresAuth: true },
      },
      {
        path: 'profile',
        name: 'profile',
        component: () => import('../views/Profile.vue'),
        meta: { title: '个人中心', requiresAuth: true },
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('../views/NotFound.vue'),
    meta: { title: '404' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 路由守卫
router.beforeEach((to, from, next) => {
  const authed = isAuthenticated()

  // 设置页面标题
  if (to.meta.title) {
    document.title = `${to.meta.title} - 设备手册知识库管理平台`
  }

  // 未登录访问受保护页 → 跳登录
  if (to.meta.requiresAuth && !authed) {
    next({ path: '/login', query: { redirect: to.fullPath } })
    return
  }

  // 已登录访问登录/注册页 → 跳首页
  if (to.meta.guestOnly && authed) {
    next('/')
    return
  }

  next()
})

export default router
