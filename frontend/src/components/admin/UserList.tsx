import React, { useState, useEffect } from 'react';
import { Button } from '../ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { Badge } from '../ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/table';
import { toast } from 'sonner';
import { api } from '../../services/api';

interface User {
  id: number;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export const UserList: React.FC = () => {
  const [users, setUsers] = useState<User[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    fetchUsers();
  }, []);

  const fetchUsers = async () => {
    try {
      const response = await api.get('/admin/users');
      setUsers(response.data);
    } catch (error: any) {
      const message = error.response?.data?.detail || 'Failed to fetch users';
      toast.error(message);
    } finally {
      setIsLoading(false);
    }
  };

  const toggleUserStatus = async (userId: number, isActive: boolean) => {
    try {
      await api.put(`/admin/users/${userId}`, { is_active: !isActive });
      toast.success(`User ${!isActive ? 'activated' : 'deactivated'} successfully`);
      fetchUsers();
    } catch (error: any) {
      const message = error.response?.data?.detail || 'Failed to update user';
      toast.error(message);
    }
  };

  const changeUserRole = async (userId: number, currentRole: string) => {
    const newRole = currentRole === 'admin' ? 'user' : 'admin';
    try {
      await api.put(`/admin/users/${userId}`, { role: newRole });
      toast.success(`User role changed to ${newRole}`);
      fetchUsers();
    } catch (error: any) {
      const message = error.response?.data?.detail || 'Failed to update user role';
      toast.error(message);
    }
  };

  if (isLoading) {
    return (
      <Card>
        <CardContent className="pt-6">
          <div className="text-center">Loading users...</div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>User Management</CardTitle>
        <CardDescription>
          Manage user accounts and permissions
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Email</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Created</TableHead>
              <TableHead>Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {users.map((user) => (
              <TableRow key={user.id}>
                <TableCell className="font-medium">{user.email}</TableCell>
                <TableCell>
                  <Badge variant={user.role === 'admin' ? 'default' : 'secondary'}>
                    {user.role}
                  </Badge>
                </TableCell>
                <TableCell>
                  <Badge variant={user.is_active ? 'default' : 'destructive'}>
                    {user.is_active ? 'Active' : 'Inactive'}
                  </Badge>
                </TableCell>
                <TableCell>
                  {new Date(user.created_at).toLocaleDateString()}
                </TableCell>
                <TableCell>
                  <div className="flex space-x-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => toggleUserStatus(user.id, user.is_active)}
                    >
                      {user.is_active ? 'Deactivate' : 'Activate'}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => changeUserRole(user.id, user.role)}
                    >
                      Make {user.role === 'admin' ? 'User' : 'Admin'}
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
};
