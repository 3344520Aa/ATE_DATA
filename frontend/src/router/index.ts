import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
    },
    {
      path: '/',
      component: () => import('@/layouts/MainLayout.vue'),
      meta: { requiresAuth: true },
      children: [
        {
          path: '',
          name: 'home',
          component: () => import('@/views/HomeView.vue'),
        },
        {
        path: 'lot/:id/param/:param',
        name: 'param',
        component: () => import('@/views/ParamView.vue'),
        },

        {
          path: 'lot/:id',
          name: 'analysis',
          component: () => import('@/views/AnalysisView.vue'),
        },
        {
          path: 'reports',
          name: 'reports',
          component: () => import('@/views/HomeView.vue'),
        },
        {
          path: 'settings',
          name: 'settings',
          component: () => import('@/views/HomeView.vue'),
        },
        {
        path: 'lot/:id/bin',
        name: 'bin',
        component: () => import('@/views/BinView.vue'),
        },
        {
          path: 'multi-analysis',
          name: 'multi-analysis',
          component: () => import('@/views/MultiAnalysisView.vue'),
        },
        {
          path: 'multi-param',
          name: 'multi-param',
          component: () => import('@/views/MultiParamView.vue'),
        },
        {
          path: 'multi-bin',
          name: 'multi-bin',
          component: () => import('@/views/MultiBinView.vue'),
        },
      ],
    },
  ],
})

router.beforeEach((to) => {
  const token = localStorage.getItem('token')
  if (to.meta.requiresAuth && !token) {
    return '/login'
  }
})

export default router