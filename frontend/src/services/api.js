import axios from 'axios';
import { authService } from './auth';

// Base URL for your backend API
const API_URL = 'https://praise-app-production.up.railway.app';

// Create axios instance with default config
const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add token to requests automatically
api.interceptors.request.use((config) => {
  const token = authService.getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// API functions
export const apiService = {
  // Auth
  register(userData) {
    return api.post('/register', userData);
  },

  login(email, password) {
    const formData = new FormData();
    formData.append('username', email); // OAuth2 uses 'username' field
    formData.append('password', password);
    return api.post('/token', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
  },

  getCurrentUser() {
    return api.get('/me');
  },

  // Core Values
  getCoreValues() {
    return api.get('/core-values');
  },

  // Praise
  givePraise(praiseData) {
    return api.post('/praise', praiseData);
  },

  getAllPraise() {
    return api.get('/praise');
  },

  getMyPraise() {
    return api.get('/praise/received');
  },

  // Rewards
  getRewards() {
    return api.get('/rewards');
  },

  redeemReward(rewardId) {
    return api.post('/redeem', { reward_id: rewardId });
  },

  getMyRedemptions() {
    return api.get('/my-redemptions');
  },
  // Admin
  getAllUsers() {
    return api.get('/users');
  },

  createCoreValue(name, description) {
    return api.post('/admin/core-values', null, {
      params: { name, description }
    });
  },

  deleteCoreValue(coreValueId) {
    return api.delete(`/admin/core-values/${coreValueId}`);
  },

  createReward(rewardData) {
    return api.post('/admin/rewards', rewardData);
  },

  deleteReward(rewardId) {
    return api.delete(`/admin/rewards/${rewardId}`);
  },

  getAllRedemptions() {
    return api.get('/admin/redemptions');
  },

  fulfillRedemption(redemptionId) {
    return api.patch(`/admin/redemptions/${redemptionId}/fulfill`);
  }
};