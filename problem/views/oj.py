from django.db.models import Q, F
from rest_framework.views import APIView

from problem.models import Problem, Solution, ProblemList, Tag
from problem.serializers import ProblemSerializer, SolutionSerializer, ProblemListSerializer, \
    ProblemListDetailSerializer, SolutionCreateSerializer, TagSerializer
from utils.api import success, fail, paginate_data, validate_serializer


class ProblemDescriptionAPI(APIView):
    @staticmethod
    def get(request, problem_id):
        """
        获取id为problem_id的题目的详细信息，包括题目的所有字段信息和请求用户的pass_status和star_status
        注：当用户未登录时，pass_status、star_status均为None
        """
        try:
            problem = Problem.objects.get(id=problem_id)
        except Problem.DoesNotExist:
            return fail('该题目不存在！')
        serializer = ProblemSerializer(problem)
        response_data = serializer.data
        response_data['similar_problems'] = problem.get_similar_problems(request.user)
        response_data['pass_status'] = problem.get_pass_status(request.user)
        response_data['star_status'] = problem.get_star_status(request.user)
        # print(response_data)
        return success(response_data)


class ProblemSolutionsAPI(APIView):
    sort_dict = {
        'likeDesc': '-like_count',
        'commentDesc': '-comment_count',
        'timeDesc': '-create_time',
        'timeAsc': 'create_time'
    }

    def get(self, request, problem_id):
        """
        获取id为problem_id的题目的所有题解信息，其中详细内容被截断为最多200个字符
        返回为一个字典列表，每个字典为一个题解的信息
        """
        try:
            problem = Problem.objects.get(id=problem_id)
        except Problem.DoesNotExist:
            return fail('该题目不存在！')
        solutions = problem.solutions.all()
        keyword = request.GET.get('keyword', None)
        tags = request.GET.get('tags', None)
        sort_type = request.GET.get('sort_type', None)
        if keyword:
            solutions = solutions.filter(content__contains=keyword)
        if tags:
            solutions = solutions.filter(tags__in=tags)
        if sort_type:
            solutions = solutions.order_by(self.sort_dict[sort_type])
        else:
            solutions = solutions.order_by('-create_time')
        solutions = paginate_data(request, solutions, SolutionSerializer)
        return success({'count': len(solutions), 'solutions': solutions})


class ProblemSolutionsDetailAPI(APIView):
    @staticmethod
    def get(request, problem_id, solution_id):
        """
        返回题解的详细信息，完整的solution_content
        """
        try:
            problem = Problem.objects.get(id=problem_id)
        except Problem.DoesNotExist:
            return fail('该题目不存在！')
        try:
            solution = problem.solutions.get(id=solution_id)
        except Solution.DoesNotExist:
            return fail('该题解不存在')

        return success(solution.content)


class ProblemListAPI(APIView):
    def get(self, request):
        """
        根据标题或简介中的关键字筛选未删除的、公开的、非请求用户自己的题单列表；如果用户未登录，则获取所有含有关键字的公开未删除题单，且题单的
        每道题目中的pass_count字段为null；
        如果关键字为空，则返回所有未删除的、公开的、非请求用户的题单；
        """
        keyword = request.GET.get('keyword', '')
        problem_lists = ProblemList.objects.filter((Q(title__icontains=keyword) | Q(summary__icontains=keyword))
                                                   & Q(is_deleted=False) & Q(is_public=True))
        if not request.user.is_authenticated:
            response_data = paginate_data(request, problem_lists, ProblemListSerializer)
            for problem_list in response_data:
                problem_list['pass_count'] = None
            return success(response_data)

        problem_lists = problem_lists.exclude(create_user=request.user)
        response_data = paginate_data(request, problem_lists, ProblemListSerializer)
        # response_data为list,problem_list为字典
        for problem_list in response_data:
            problem_list['pass_count'] = 0
            # problem_list['id']取自于数据库，可保证存在，不需要处理异常
            for problem in ProblemList.objects.get(id=problem_list['id']).problems.all():
                if problem.get_pass_status(request.user):
                    problem_list['pass_count'] += 1

        return success(response_data)


class ProblemListDetailAPI(APIView):
    def get(self, request, problemlist_id):
        """
        获取id为problemlist_id的题单的详细信息。
        用户未登录时或题单id不存在时，返回对应的错误信息
        """
        if not request.user.is_authenticated:
            return fail("用户未登录！")
        try:
            problem_list = ProblemList.objects.get(id=problemlist_id)
        except ProblemList.DoesNotExist:
            return fail("该题单不存在！")

        response_data = ProblemListDetailSerializer(problem_list).data
        response_data['star_status'] = problem_list.get_star_status(request.user)
        problems = response_data['problems']
        for problem in problems:
            problem['pass_status'] = Problem.objects.get(id=problem['id']).get_pass_status(request.user)

        return success(response_data)

    def put(self, request, problemlist_id):
        """
        向题单添加或删除题目，路径中有一个problemlist_id参数，另外需要传递problem_ids和is_add两个字段，
        problem_ids表示需要操作的题目id列表，is_add表示操作为添加或删除
        当用户未登录或题单创建者不是请求用户或题单不存在时返回相应的错误
        当添加的题目已经存在题单或删除的题目不在题单之中，返回相应的错误
        """
        problem_ids = request.data['problem_ids']
        is_add = request.data['is_add']
        problems = Problem.objects.filter(id__in=problem_ids)
        try:
            problem_list = ProblemList.objects.get(id=problemlist_id)
        except ProblemList.DoesNotExist:
            return fail("该题单不存在！")
        if not request.user.is_authenticated or problem_list.create_user != request.user:
            return fail('用户无权限！')

        if is_add:
            if problem_list.problems.filter(id__in=problem_ids).count() == len(problem_ids):
                return fail('添加的题目已经存在于题单之中！')
            problems_in_list = problem_list.problems.filter(id__in=problem_ids)
            problem_list.add_problem(problems.difference(problems_in_list))
            return success("添加成功")

        if problem_list.problems.filter(id__in=problem_ids).count() != 0:
            problems_in_list = problem_list.problems.filter(id__in=problem_ids)
            problem_list.remove_problem(problems_in_list)
            return success("删除成功")
        else:
            return fail('删除的题目不在题单之中')

    def delete(self, request, problemlist_id):
        """
        删除一个题单，如果题单收藏数为0，直接删除记录，否则软删除，只是将is_deleted字段设为true，使其不会被get出来，当收藏数为0时再硬删除
        当题单不存在或用户未登录或请求用户非创建者时返回相应的错误
        """
        try:
            problem_list = ProblemList.objects.get(id=problemlist_id)
        except ProblemList.DoesNotExist:
            return fail('该题单不存在！')
        if not request.user.is_authenticated or problem_list.create_user != request.user:
            return fail('用户无权限！')

        if problem_list.star_users.exists():
            problem_list.is_deleted = True
            problem_list.save()
        else:
            problem_list.delete()
        return success("删除成功")


class ProblemListStarAPI(APIView):
    def post(self, request):
        """
        收藏/取消收藏一个题单
        用户未登录或题单不存在时返回相应错误
        当被取消收藏的题单收藏数为0时
        """
        if not request.user.is_authenticated:
            return fail('用户未登录！')
        try:
            problem_list = ProblemList.objects.get(id=request.data['problemlist_id'])
        except ProblemList.DoesNotExist:
            return fail('不存在该题单！')
        if problem_list.star_users.contains(request.user):
            problem_list.star_users.remove(request.user)
            problem_list.remove_star_count()
            if not problem_list.star_users.exists() and problem_list.is_deleted:
                problem_list.delete()
            return success('取消收藏！')
        else:
            problem_list.star_users.add(request.user)
            problem_list.add_star_count()
            return success('收藏成功！')


class ProblemSolutionCreateAPI(APIView):
    @validate_serializer(SolutionCreateSerializer)
    def post(self, request):
        if not request.user.is_authenticated:
            return fail("用户未登录！")
        try:
            problem = Problem.objects.get(id=request.data['problem_id'])
        except Problem.DoesNotExist:
            return fail("不存在该题目！")
        tags = Tag.objects.filter(id__in=request.data.get('tags', []))
        solution = Solution.objects.create(content=request.data['content'], problem=problem,
                                           create_user=request.user)
        solution.tags.set(tags)
        solution.last_update_time = solution.create_time
        solution.save()
        return success('创建成功')


class TagAPI(APIView):
    def get(self, request):
        tags = Tag.objects.all()
        serializer = TagSerializer(tags, many=True)
        return success(serializer.data)


class ProblemsetAPI(APIView):
    def get(self, request):
        pass
