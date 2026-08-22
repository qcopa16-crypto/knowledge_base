import request from './request'

// 品牌列表
export function getBrands(params) {
  return request.get('/catalog/brands/', { params })
}

// 新增品牌
export function createBrand(data) {
  return request.post('/catalog/brands/', data)
}

// 更新品牌
export function updateBrand(id, data) {
  return request.patch(`/catalog/brands/${id}/`, data)
}

// 删除品牌
export function deleteBrand(id) {
  return request.delete(`/catalog/brands/${id}/`)
}

// 设备类型列表
export function getDeviceTypes(params) {
  return request.get('/catalog/device-types/', { params })
}

// 新增设备类型
export function createDeviceType(data) {
  return request.post('/catalog/device-types/', data)
}

// 更新设备类型
export function updateDeviceType(id, data) {
  return request.patch(`/catalog/device-types/${id}/`, data)
}

// 删除设备类型
export function deleteDeviceType(id) {
  return request.delete(`/catalog/device-types/${id}/`)
}

// 分类列表
export function getCategories(params) {
  return request.get('/catalog/categories/', { params })
}

// 分类树
export function getCategoryTree() {
  return request.get('/catalog/categories/tree/')
}

// 新增分类
export function createCategory(data) {
  return request.post('/catalog/categories/', data)
}

// 更新分类
export function updateCategory(id, data) {
  return request.patch(`/catalog/categories/${id}/`, data)
}

// 删除分类
export function deleteCategory(id) {
  return request.delete(`/catalog/categories/${id}/`)
}
